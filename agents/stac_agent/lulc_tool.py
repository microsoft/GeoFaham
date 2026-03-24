# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

esir_classes = {
    'No Data': 0,
    'Water': 1,
    'Trees': 2,
    'Flooded vegetation': 4,
    'Crops': 5,
    'Built area': 7,
    'Bare ground': 8,
    'Snow/ice': 9,
    'Clouds': 10,
    'Rangeland': 11
}

esa_classes = {
    "Tree cover": 10,
    "Shrubland": 20,
    "Grassland": 30,
    "Cropland": 40,
    "Built-up": 50,
    "Bare / sparse vegetation": 60,
    "Snow and ice": 70,
    "Permanent water bodies": 80,
    "Herbaceous wetland": 90,
    "Mangroves": 95,
    "Moss and lichen": 100
}



#  Value ┃ Description              ┃ Hex Color ┃
# ┡━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━┩
# │ 10    │ Tree cover               │ 006400    │
# │ 20    │ Shrubland                │ FFBB22    │
# │ 30    │ Grassland                │ FFFF4C    │
# │ 40    │ Cropland                 │ F096FF    │
# │ 50    │ Built-up                 │ FA0000    │
# │ 60    │ Bare / sparse vegetation │ B4B4B4    │
# │ 70    │ Snow and ice             │ F0F0F0    │
# │ 80    │ Permanent water bodies   │ 0064C8    │
# │ 90    │ Herbaceous wetland       │ 0096A0    │
# │ 95    │ Mangroves                │ 00CF75    │
# │ 100   │ Moss and lichen          │ FAE6A0 