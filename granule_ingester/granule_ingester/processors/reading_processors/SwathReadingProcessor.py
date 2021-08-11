from typing import Dict

import numpy as np
import xarray as xr
from nexusproto import DataTile_pb2 as nexusproto
from nexusproto.serialization import to_shaped_array

from granule_ingester.processors.reading_processors.TileReadingProcessor import TileReadingProcessor


class SwathReadingProcessor(TileReadingProcessor):
    def __init__(self, variable, latitude, longitude, time, depth=None, **kwargs):
        super().__init__(variable, latitude, longitude, **kwargs)
        if isinstance(variable, list) and len(variable) != 1:
            raise RuntimeError(f'TimeSeriesReadingProcessor does not support multiple variable: {variable}')
        self.depth = depth
        self.time = time

    def _generate_tile(self, ds: xr.Dataset, dimensions_to_slices: Dict[str, slice], input_tile):
        data_variable = self.variable[0] if isinstance(self.variable, list) else self.variable
        new_tile = nexusproto.SwathTile()

        lat_subset = ds[self.latitude][type(self)._slices_for_variable(ds[self.latitude], dimensions_to_slices)]
        lon_subset = ds[self.longitude][type(self)._slices_for_variable(ds[self.longitude], dimensions_to_slices)]
        lat_subset = np.ma.filled(lat_subset, np.NaN)
        lon_subset = np.ma.filled(lon_subset, np.NaN)

        time_subset = ds[self.time][type(self)._slices_for_variable(ds[self.time], dimensions_to_slices)]
        time_subset = np.ma.filled(type(self)._convert_to_timestamp(time_subset), np.NaN)

        data_subset = ds[data_variable][type(self)._slices_for_variable(ds[data_variable],
                                                                                dimensions_to_slices)]
        data_subset = np.ma.filled(data_subset, np.NaN)

        if self.depth:
            depth_dim, depth_slice = list(type(self)._slices_for_variable(ds[self.depth],
                                                                          dimensions_to_slices).items())[0]
            depth_slice_len = depth_slice.stop - depth_slice.start
            if depth_slice_len > 1:
                raise RuntimeError(
                    "Depth slices must have length 1, but '{dim}' has length {dim_len}.".format(dim=depth_dim,
                                                                                                dim_len=depth_slice_len))
            new_tile.depth = ds[self.depth][depth_slice].item()

        new_tile.latitude.CopyFrom(to_shaped_array(lat_subset))
        new_tile.longitude.CopyFrom(to_shaped_array(lon_subset))
        new_tile.variable_data.CopyFrom(to_shaped_array(data_subset))
        new_tile.time.CopyFrom(to_shaped_array(time_subset))
        input_tile.tile.swath_tile.CopyFrom(new_tile)
        return input_tile
