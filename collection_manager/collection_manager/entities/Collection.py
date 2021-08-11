import json
import logging
import os
import pathlib
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from fnmatch import fnmatch
from glob import glob
from typing import List, Optional
from urllib.parse import urlparse

from collection_manager.entities.exceptions import MissingValueCollectionError

logger = logging.getLogger(__name__)

class CollectionStorageType(Enum):
    LOCAL = 1
    S3 = 2


@dataclass(frozen=True)
class Collection:
    dataset_id: str
    projection: str
    dimension_names: frozenset
    slices: frozenset
    path: str
    historical_priority: int
    forward_processing_priority: Optional[int] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None

    @staticmethod
    def __decode_dimension_names(dimension_names_dict):
        """
        - Validating both `variable` and `variables` are not part of the dictionary
        - if it has `variable`, converting it to single element list
        - if it has `variables`, keeping it as a list while renmaing the key to `variable`
        """
        if 'variable' in dimension_names_dict and 'variables' in dimension_names_dict:
            raise RuntimeError('both variable and variables present in dimensionNames. Only one is allowed')
        new_dimension_names = [(k, v) for k, v in dimension_names_dict.items() if k not in ['variable', 'variables']]
        if 'variable' in dimension_names_dict:
            if not isinstance(dimension_names_dict['variable'], str):
                raise RuntimeError(f'variable in dimensionNames must be string type. value: {dimension_names_dict["variable"]}')
            new_dimension_names.append(('variable', json.dumps(dimension_names_dict['variable'])))
            return new_dimension_names
        if 'variables' in dimension_names_dict:
            if not isinstance(dimension_names_dict['variables'], list):
                raise RuntimeError(f'variable in dimensionNames must be list type. value: {dimension_names_dict["variables"]}')
            new_dimension_names.append(('variable', json.dumps(dimension_names_dict['variables'])))
            return new_dimension_names

    @staticmethod
    def from_dict(properties: dict):
        """
        Accepting either `variable` or `variables` from the configmap
        """
        logger.debug(f'incoming properties dict: {properties}')
        try:
            date_to = datetime.fromisoformat(properties['to']) if 'to' in properties else None
            date_from = datetime.fromisoformat(properties['from']) if 'from' in properties else None

            collection = Collection(dataset_id=properties['id'],
                                    projection=properties['projection'],
                                    dimension_names=frozenset(Collection.__decode_dimension_names(properties['dimensionNames'])),
                                    slices=frozenset(properties['slices'].items()),
                                    path=properties['path'],
                                    historical_priority=properties['priority'],
                                    forward_processing_priority=properties.get('forward-processing-priority', None),
                                    date_to=date_to,
                                    date_from=date_from)
            return collection
        except KeyError as e:
            raise MissingValueCollectionError(missing_value=e.args[0])

    def storage_type(self):
        if urlparse(self.path).scheme == 's3':
            return CollectionStorageType.S3
        else:
            return CollectionStorageType.LOCAL

    def directory(self):
        if urlparse(self.path).scheme == 's3':
            return self.path
        elif os.path.isdir(self.path):
            return self.path
        else:
            return os.path.dirname(self.path)

    def owns_file(self, file_path: str) -> bool:
        if urlparse(file_path).scheme == 's3':
            return file_path.find(self.path) == 0
        else:
            if os.path.isdir(file_path):
                raise IsADirectoryError()

            if os.path.isdir(self.path):
                return pathlib.Path(self.path) in pathlib.Path(file_path).parents
            else:
                return fnmatch(file_path, self.path)
