# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import numpy
from nexusproto import DataTile_pb2 as nexusproto
from nexusproto.serialization import from_shaped_array

from granule_ingester.processors.TileProcessor import TileProcessor


class NoTimeException(Exception):
    pass


def find_time_min_max(tile_data):
    if tile_data.time:
        if isinstance(tile_data.time, nexusproto.ShapedArray):
            time_data = from_shaped_array(tile_data.time)
            return int(numpy.nanmin(time_data).item()), int(numpy.nanmax(time_data).item())
        elif isinstance(tile_data.time, int):
            return tile_data.time, tile_data.time

    raise NoTimeException


class TileSummarizingProcessor(TileProcessor):

    def __init__(self, dataset_name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dataset_name = dataset_name

    def process(self, tile, dataset, *args, **kwargs):
        tile_type = tile.tile.WhichOneof("tile_type")
        tile_data = getattr(tile.tile, tile_type)

        latitudes = numpy.ma.masked_invalid(from_shaped_array(tile_data.latitude))
        longitudes = numpy.ma.masked_invalid(from_shaped_array(tile_data.longitude))
        data = from_shaped_array(tile_data.variable_data)

        tile_summary = tile.summary if tile.HasField("summary") else nexusproto.TileSummary()

        tile_summary.dataset_name = self._dataset_name
        tile_summary.bbox.lat_min = numpy.nanmin(latitudes).item()
        tile_summary.bbox.lat_max = numpy.nanmax(latitudes).item()
        tile_summary.bbox.lon_min = numpy.nanmin(longitudes).item()
        tile_summary.bbox.lon_max = numpy.nanmax(longitudes).item()
        tile_summary.stats.min = numpy.nanmin(data).item()
        tile_summary.stats.max = numpy.nanmax(data).item()
        tile_summary.stats.count = data.size - numpy.count_nonzero(numpy.isnan(data))

        # In order to accurately calculate the average we need to weight the data based on the cosine of its latitude
        # This is handled slightly differently for swath vs. grid data
        if tile_type == 'swath_tile':
            # For Swath tiles, len(data) == len(latitudes) == len(longitudes).
            # So we can simply weight each element in the data array
            tile_summary.stats.mean = type(self).calculate_mean_for_swath_tile(data, latitudes)
        elif tile_type == 'grid_tile':
            # Grid tiles need to repeat the weight for every longitude
            # TODO This assumes data axis' are ordered as latitude x longitude
            tile_summary.stats.mean = type(self).calculate_mean_for_grid_tile(data, latitudes, longitudes)
        else:
            # Default to simple average with no weighting
            tile_summary.stats.mean = numpy.nanmean(data).item()

        try:
            min_time, max_time = find_time_min_max(tile_data)
            tile_summary.stats.min_time = min_time
            tile_summary.stats.max_time = max_time
        except NoTimeException:
            pass

        standard_name = dataset.variables[tile_summary.data_var_name].attrs.get('standard_name')
        if standard_name:
            tile_summary.standard_name = standard_name

        tile.summary.CopyFrom(tile_summary)
        return tile

    @staticmethod
    def calculate_mean_for_grid_tile(variable_data, latitudes, longitudes):
        flattened_variable_data = numpy.ma.masked_invalid(variable_data).flatten()
        repeated_latitudes = numpy.repeat(latitudes, len(longitudes))
        weights = numpy.cos(numpy.radians(repeated_latitudes))
        return numpy.ma.average(flattened_variable_data, weights=weights).item()

    @staticmethod
    def calculate_mean_for_swath_tile(variable_data, latitudes):
        weights = numpy.cos(numpy.radians(latitudes))
        return numpy.ma.average(numpy.ma.masked_invalid(variable_data),
                                weights=weights).item()
