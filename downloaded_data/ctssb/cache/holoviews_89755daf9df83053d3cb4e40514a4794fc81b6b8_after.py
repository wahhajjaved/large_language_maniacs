from collections import OrderedDict

import numpy as np

import param

from ..core import NdMapping
from holoviews.core.element import HoloMap
from ..core.operation import MapOperation
from ..element import Table, Curve


class table_collate(MapOperation):

    collation_dim = param.String(default="")

    def _process(self, vmap):
        collate_dim = self.p.collation_dim
        new_dimensions = [d for d in vmap.key_dimensions if d.name != collate_dim]
        nested_map = vmap.groupby([collate_dim]) if new_dimensions else {(): vmap}
        collate_dim = vmap.get_dimension(collate_dim)

        table = vmap.last
        table_dims = table.key_dimensions
        if isinstance(vmap.last, Table):
            outer_dims = table_dims[-2:]
            new_dimensions += [td for td in table_dims if td not in outer_dims]
            entry_keys = [k[-2:] for k in table.data.keys()]
        else:
            outer_dims = ['Label']
            entry_keys = table.data.keys()

        # Generate a HoloMap for every entry in the table
        map_fn = lambda: HoloMap(**dict(vmap.get_param_values(), key_dimensions=new_dimensions))
        entries = [(entry, map_fn() if new_dimensions else None) for entry in entry_keys]
        maps = NdMapping(entries, key_dimensions=outer_dims)
        for new_key, collate_map in nested_map.items():
            curve_data = OrderedDict((k, []) for k in entry_keys)
            # Get the x- and y-values for each entry in the ItemTable
            xvalues = [float(k) for k in collate_map.keys()]
            for x, table in collate_map.items():
                for label, value in table.data.items():
                    entry_key = label[-2:] if isinstance(table, Table) else label
                    curve_data[entry_key].append(float(value))

            # Generate curves with correct dimensions
            for label, yvalues in curve_data.items():
                settings = dict(key_dimensions=[collate_dim])
                if isinstance(table, Table):
                    if not isinstance(label, tuple): label = (label,)
                    if not isinstance(new_key, tuple): new_key = (new_key,)
                    settings.update(value=table.value, label=table.label,
                                    key_dimensions=[collate_dim])
                    key = new_key + label[0:max(0,len(label)-2)]
                    label = label[-2:]
                else:
                    key = new_key
                    value = table.get_dimension(label)
                    settings.update(value_dimensions=[value], label=table.label,
                                    value=table.value)
                curve = Curve(zip(xvalues, yvalues), **settings)
                if new_dimensions:
                    maps[label][key] = curve
                else:
                    maps[label] = curve

        # If there are multiple table entries, generate grid
        maps = HoloMap(maps.items(), **dict(maps.get_param_values()))
        if isinstance(table, Table):
            if len(maps) > 1:
                grid = maps.grid([d.name for d in maps.key_dimensions])
            else:
                grid = maps.last
        else:
            if len(maps) > 1:
                grid = maps.values()[0]
                for item in maps.values()[1:]:
                    grid += item
            else:
                grid = maps.last
        return grid
