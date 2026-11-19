### Ceiling check: stnet_fault_s42

SYNTHETIC faults, held-out validation years only. Budget 1 false alerts per 1,000 clean cell-days (threshold 1.114). Strong = change >= 5 mm and footprint weight >= 0.5.

Overall recall 0.652 (n=29098); recall on strong cell-days 0.798 (n=1888).
Share of fault cell-days: change under 1 mm 56.1%, weight under 0.5 86.6%, strong 6.5%.

| change (mm) | recall |
|---|---|
| 0-0.1 | 0.471 (n=6038) |
| 0.1-1 | 0.596 (n=10297) |
| 1-5 | 0.722 (n=6980) |
| 5-20 | 0.830 (n=3567) |
| 20-100 | 0.899 (n=2004) |
| 100-inf | 0.915 (n=212) |

| footprint weight | recall |
|---|---|
| 0-0.25 | 0.651 (n=20709) |
| 0.25-0.5 | 0.658 (n=4501) |
| 0.5-0.75 | 0.798 (n=1297) |
| 0.75-1 | 0.579 (n=2591) |

| kind | all | centre cells | strong | share under 1 mm |
|---|---|---|---|---|
| combination | 0.906 (n=12428) | 0.773 (n=986) | 0.941 (n=1093) | 44.6% |
| drift | 0.023 (n=5303) | 0.040 (n=604) | 0.046 (n=152) | 77.4% |
| phantom_rain | 0.833 (n=4196) | 0.912 (n=411) | - | 77.9% |
| scale | 0.037 (n=1700) | 0.219 (n=146) | 0.223 (n=121) | 53.1% |
| spike | 0.870 (n=1212) | 0.974 (n=78) | 0.940 (n=134) | 15.5% |
| stuck | 0.886 (n=3343) | 0.857 (n=252) | 0.906 (n=340) | 51.3% |
| zeroed | 0.022 (n=916) | 0.123 (n=114) | 0.208 (n=48) | 67.1% |

Recall of the CENTRE cell, by footprint radius of its event (single cell = no neighbour is faulty):

| kind | single cell | radius 1.5-2.5 | radius 2.5-4 | radius above 4 |
|---|---|---|---|---|
| combination | 0.628 (n=529) | 0.878 (n=131) | 0.966 (n=326) | - |
| drift | 0.035 (n=316) | 0.007 (n=135) | 0.078 (n=153) | - |
| phantom_rain | 0.902 (n=234) | 0.945 (n=73) | 0.913 (n=104) | - |
| scale | 0.333 (n=75) | 0.227 (n=22) | 0.041 (n=49) | - |
| spike | 1.000 (n=30) | 1.000 (n=19) | 0.931 (n=29) | - |
| stuck | 0.795 (n=132) | 0.862 (n=58) | 0.984 (n=62) | - |
| zeroed | 0.219 (n=64) | 0.000 (n=26) | 0.000 (n=24) | - |

All cell-days, by footprint radius: single cell 0.528 (n=1380); radius 1.5-2.5 0.635 (n=5724); radius 2.5-4 0.664 (n=21994); radius above 4 -

Recall by the memory a long-memory model has at that day (history days + day of the year; a drift that starts early has little baseline):

| memory | all | drift | scale | zeroed |
|---|---|---|---|---|
| memory 90-179 d | 0.847 (n=7820) | 0.016 (n=696) | 0.254 (n=63) | 0.000 (n=24) |
| memory 180-269 d | 0.552 (n=6349) | 0.037 (n=2032) | 0.082 (n=195) | 0.024 (n=254) |
| memory 270-364 d | 0.422 (n=8434) | 0.006 (n=1990) | 0.022 (n=1391) | 0.026 (n=420) |
| memory 365+ d | 0.815 (n=6495) | 0.038 (n=585) | 0.020 (n=51) | 0.014 (n=218) |

### Ceiling check: stnet_clean_s42

SYNTHETIC faults, held-out validation years only. Budget 1 false alerts per 1,000 clean cell-days (threshold 1.546). Strong = change >= 5 mm and footprint weight >= 0.5.

Overall recall 0.304 (n=29098); recall on strong cell-days 0.784 (n=1888).
Share of fault cell-days: change under 1 mm 56.1%, weight under 0.5 86.6%, strong 6.5%.

| change (mm) | recall |
|---|---|
| 0-0.1 | 0.008 (n=6038) |
| 0.1-1 | 0.058 (n=10297) |
| 1-5 | 0.468 (n=6980) |
| 5-20 | 0.817 (n=3567) |
| 20-100 | 0.908 (n=2004) |
| 100-inf | 0.953 (n=212) |

| footprint weight | recall |
|---|---|
| 0-0.25 | 0.235 (n=20709) |
| 0.25-0.5 | 0.448 (n=4501) |
| 0.5-0.75 | 0.549 (n=1297) |
| 0.75-1 | 0.489 (n=2591) |

| kind | all | centre cells | strong | share under 1 mm |
|---|---|---|---|---|
| combination | 0.473 (n=12428) | 0.667 (n=986) | 0.929 (n=1093) | 44.6% |
| drift | 0.006 (n=5303) | 0.010 (n=604) | 0.033 (n=152) | 77.4% |
| phantom_rain | 0.118 (n=4196) | 0.701 (n=411) | - | 77.9% |
| scale | 0.037 (n=1700) | 0.192 (n=146) | 0.215 (n=121) | 53.1% |
| spike | 0.754 (n=1212) | 0.987 (n=78) | 0.955 (n=134) | 15.5% |
| stuck | 0.441 (n=3343) | 0.833 (n=252) | 0.897 (n=340) | 51.3% |
| zeroed | 0.001 (n=916) | 0.009 (n=114) | 0.021 (n=48) | 67.1% |

Recall of the CENTRE cell, by footprint radius of its event (single cell = no neighbour is faulty):

| kind | single cell | radius 1.5-2.5 | radius 2.5-4 | radius above 4 |
|---|---|---|---|---|
| combination | 0.552 (n=529) | 0.870 (n=131) | 0.773 (n=326) | - |
| drift | 0.006 (n=316) | 0.007 (n=135) | 0.020 (n=153) | - |
| phantom_rain | 0.791 (n=234) | 0.781 (n=73) | 0.442 (n=104) | - |
| scale | 0.253 (n=75) | 0.182 (n=22) | 0.102 (n=49) | - |
| spike | 1.000 (n=30) | 1.000 (n=19) | 0.966 (n=29) | - |
| stuck | 0.811 (n=132) | 0.776 (n=58) | 0.935 (n=62) | - |
| zeroed | 0.000 (n=64) | 0.000 (n=26) | 0.042 (n=24) | - |

All cell-days, by footprint radius: single cell 0.460 (n=1380); radius 1.5-2.5 0.274 (n=5724); radius 2.5-4 0.302 (n=21994); radius above 4 -

Recall by the memory a long-memory model has at that day (history days + day of the year; a drift that starts early has little baseline):

| memory | all | drift | scale | zeroed |
|---|---|---|---|---|
| memory 90-179 d | 0.393 (n=7820) | 0.010 (n=696) | 0.095 (n=63) | 0.000 (n=24) |
| memory 180-269 d | 0.245 (n=6349) | 0.004 (n=2032) | 0.067 (n=195) | 0.000 (n=254) |
| memory 270-364 d | 0.168 (n=8434) | 0.004 (n=1990) | 0.031 (n=1391) | 0.002 (n=420) |
| memory 365+ d | 0.432 (n=6495) | 0.010 (n=585) | 0.020 (n=51) | 0.000 (n=218) |

### Ceiling check: stnet_disc_s42

SYNTHETIC faults, held-out validation years only. Budget 1 false alerts per 1,000 clean cell-days (threshold 6.253). Strong = change >= 5 mm and footprint weight >= 0.5.

Overall recall 0.032 (n=29098); recall on strong cell-days 0.338 (n=1888).
Share of fault cell-days: change under 1 mm 56.1%, weight under 0.5 86.6%, strong 6.5%.

| change (mm) | recall |
|---|---|
| 0-0.1 | 0.000 (n=6038) |
| 0.1-1 | 0.001 (n=10297) |
| 1-5 | 0.001 (n=6980) |
| 5-20 | 0.001 (n=3567) |
| 20-100 | 0.358 (n=2004) |
| 100-inf | 0.868 (n=212) |

| footprint weight | recall |
|---|---|
| 0-0.25 | 0.004 (n=20709) |
| 0.25-0.5 | 0.045 (n=4501) |
| 0.5-0.75 | 0.107 (n=1297) |
| 0.75-1 | 0.193 (n=2591) |

| kind | all | centre cells | strong | share under 1 mm |
|---|---|---|---|---|
| combination | 0.055 (n=12428) | 0.373 (n=986) | 0.456 (n=1093) | 44.6% |
| drift | 0.003 (n=5303) | 0.007 (n=604) | 0.026 (n=152) | 77.4% |
| phantom_rain | 0.000 (n=4196) | 0.000 (n=411) | - | 77.9% |
| scale | 0.015 (n=1700) | 0.103 (n=146) | 0.132 (n=121) | 53.1% |
| spike | 0.120 (n=1212) | 0.769 (n=78) | 0.507 (n=134) | 15.5% |
| stuck | 0.016 (n=3343) | 0.206 (n=252) | 0.153 (n=340) | 51.3% |
| zeroed | 0.002 (n=916) | 0.000 (n=114) | 0.000 (n=48) | 67.1% |

Recall of the CENTRE cell, by footprint radius of its event (single cell = no neighbour is faulty):

| kind | single cell | radius 1.5-2.5 | radius 2.5-4 | radius above 4 |
|---|---|---|---|---|
| combination | 0.329 (n=529) | 0.374 (n=131) | 0.445 (n=326) | - |
| drift | 0.013 (n=316) | 0.000 (n=135) | 0.000 (n=153) | - |
| phantom_rain | 0.000 (n=234) | 0.000 (n=73) | 0.000 (n=104) | - |
| scale | 0.133 (n=75) | 0.000 (n=22) | 0.102 (n=49) | - |
| spike | 0.967 (n=30) | 0.737 (n=19) | 0.586 (n=29) | - |
| stuck | 0.235 (n=132) | 0.138 (n=58) | 0.210 (n=62) | - |
| zeroed | 0.000 (n=64) | 0.000 (n=26) | 0.000 (n=24) | - |

All cell-days, by footprint radius: single cell 0.180 (n=1380); radius 1.5-2.5 0.022 (n=5724); radius 2.5-4 0.025 (n=21994); radius above 4 -

Recall by the memory a long-memory model has at that day (history days + day of the year; a drift that starts early has little baseline):

| memory | all | drift | scale | zeroed |
|---|---|---|---|---|
| memory 90-179 d | 0.031 (n=7820) | 0.001 (n=696) | 0.032 (n=63) | 0.000 (n=24) |
| memory 180-269 d | 0.033 (n=6349) | 0.003 (n=2032) | 0.021 (n=195) | 0.000 (n=254) |
| memory 270-364 d | 0.015 (n=8434) | 0.004 (n=1990) | 0.013 (n=1391) | 0.005 (n=420) |
| memory 365+ d | 0.051 (n=6495) | 0.002 (n=585) | 0.020 (n=51) | 0.000 (n=218) |
