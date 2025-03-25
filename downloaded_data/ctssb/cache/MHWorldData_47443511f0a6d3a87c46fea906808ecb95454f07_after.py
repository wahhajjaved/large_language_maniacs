import csv

import mhdata.typecheck as typecheck
import mhdata.util as util

def determine_fields(obj_list):
    """
    Returns the set of all possible keys in the object list
    """
    fields = []
    for obj in obj_list:
        for key in obj.keys():
            if key not in fields:
                fields.append(key)

    return fields

def validate_csv(obj_list, filename):
    "Minor validation. Warning for any key/value without whitespace"
    warn_keys = False
    warn_value_rows = []
    for idx, item in enumerate(obj_list):
        for key in item.keys():
            if key.startswith(" ") or key.endswith(" "):
                warn_keys = True

        for value in item.values():
            if value is None:
                continue

            if value.startswith(" ") or value.endswith(" "):
                warn_value_rows.append(idx)
                break
                
    if warn_keys:
        print("Warning: Some keys in CSV are not trimmed: " + filename)
    if warn_value_rows:
        print("Warning: Some values in CSV are not trimmed: "
            + filename + " rows: " + ", ".join(warn_value_rows))


def save_csv(obj_list, location):
    """Saves a dict list as a  CSV, doing some last minute validations. 
    Fields are auto-determined"""

    if not typecheck.is_flat_dict_list(obj_list):
        raise Exception("Cannot save CSV, the data is not completely flat")

    fields = determine_fields(obj_list)
    with open(location, 'w', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(obj_list)


def read_csv(location):
    "Reads a csv file as an object list without additional processing"
    with open(location, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        items = list(reader)

        # CSV does not distinguish between empty string and null
        # Set empties to null
        for item in items:
            for key, value in item.items():
                if value == '':
                    item[key] = None

        validate_csv(items, location)
            
        return items
