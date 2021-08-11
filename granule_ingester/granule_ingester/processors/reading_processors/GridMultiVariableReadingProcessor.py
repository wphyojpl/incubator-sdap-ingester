import logging
from typing import Dict

import numpy as np
import xarray as xr
from granule_ingester.processors.reading_processors.MultiBandUtils import MultiBandUtils
from nexusproto import DataTile_pb2 as nexusproto
from nexusproto.serialization import to_shaped_array

from granule_ingester.processors.reading_processors.TileReadingProcessor import TileReadingProcessor

logger = logging.getLogger(__name__)


class GridMultiVariableReadingProcessor(TileReadingProcessor):
    def __init__(self, variable, latitude, longitude, depth=None, time=None, **kwargs):
        super().__init__(variable, latitude, longitude, **kwargs)
        self.depth = depth
        self.time = time

    def _generate_tile(self, ds: xr.Dataset, dimensions_to_slices: Dict[str, slice], input_tile):
        """
        Update 2021-05-28 : adding support for banded datasets
            - self.variable can be a string or a list of strings
            - if it is a string, keep the original workflow
            - if it is a list, loop over the variable property array which will be the name of several datasets
            - dimension 0 will be the defined list of datasets from parameters
            - dimension 1 will be latitude
            - dimension 2 will be longitude
            - need to switch the dimensions
            - dimension 0: latitude, dimension 1: longitude, dimension 2: defined list of datasets from parameters
        Update 2021-07-09: temporarily cancelling dimension switches as it means lots of changes on query side.
        :param ds: xarray.Dataset - netcdf4 object
        :param dimensions_to_slices: Dict[str, slice] - slice dict with keys as the keys of the netcdf4 datasets
        :param input_tile: nexusproto.NexusTile()
        :return: input_tile - filled with the value
        """
        new_tile = nexusproto.GridMultiVariableTile()

        lat_subset = ds[self.latitude][type(self)._slices_for_variable(ds[self.latitude], dimensions_to_slices)]
        lon_subset = ds[self.longitude][type(self)._slices_for_variable(ds[self.longitude], dimensions_to_slices)]
        lat_subset = np.ma.filled(np.squeeze(lat_subset), np.NaN)
        lon_subset = np.ma.filled(np.squeeze(lon_subset), np.NaN)

        if not isinstance(self.variable, list):
            raise ValueError(f'self.variable `{self.variable}` needs to be a list. use GridReadingProcessor for single band Grid files.')
        logger.debug(f'reading as banded grid as self.variable is a list. self.variable: {self.variable}')
        if len(self.variable) < 1:
            raise ValueError(f'list of variable is empty. Need at least 1 variable')
        data_subset = [ds[k][type(self)._slices_for_variable(ds[k], dimensions_to_slices)] for k in self.variable]
        updated_dims, updated_dims_indices = MultiBandUtils.move_band_dimension(list(data_subset[0].dims))
        logger.debug(f'filling the data_subset with NaN')
        data_subset = np.ma.filled(data_subset, np.NaN)
        logger.debug(f'transposing data_subset')
        data_subset = data_subset.transpose(updated_dims_indices)
        logger.debug(f'adding summary.data_dim_names')
        input_tile.summary.data_dim_names.extend(updated_dims)
        if self.depth:
            depth_dim, depth_slice = list(type(self)._slices_for_variable(ds[self.depth],
                                                                          dimensions_to_slices).items())[0]
            depth_slice_len = depth_slice.stop - depth_slice.start
            if depth_slice_len > 1:
                raise RuntimeError(
                    "Depth slices must have length 1, but '{dim}' has length {dim_len}.".format(dim=depth_dim,
                                                                                                dim_len=depth_slice_len))
            new_tile.depth = ds[self.depth][depth_slice].item()

        if self.time:
            time_slice = dimensions_to_slices[self.time]
            time_slice_len = time_slice.stop - time_slice.start
            if time_slice_len > 1:
                raise RuntimeError(
                    "Time slices must have length 1, but '{dim}' has length {dim_len}.".format(dim=self.time,
                                                                                               dim_len=time_slice_len))
            new_tile.time = int(ds[self.time][time_slice.start].item() / 1e9)

        new_tile.latitude.CopyFrom(to_shaped_array(lat_subset))
        new_tile.longitude.CopyFrom(to_shaped_array(lon_subset))
        new_tile.variable_data.CopyFrom(to_shaped_array(data_subset))

        input_tile.tile.grid_multi_variable_tile.CopyFrom(new_tile)
        return input_tile
