### Ceiling check: stnet_zeroed_s42

SYNTHETIC faults, held-out validation years only. Budget 1 false alerts per 1,000 clean cell-days (threshold 0.097). Strong = change >= 5 mm and footprint weight >= 0.5.

Overall recall 0.018 (n=29098); recall on strong cell-days 0.029 (n=1888).
Share of fault cell-days: change under 1 mm 56.1%, weight under 0.5 86.6%, strong 6.5%.

| change (mm) | recall |
|---|---|
| 0-0.1 | 0.014 (n=6038) |
| 0.1-1 | 0.022 (n=10297) |
| 1-5 | 0.019 (n=6980) |
| 5-20 | 0.014 (n=3567) |
| 20-100 | 0.007 (n=2004) |
| 100-inf | 0.005 (n=212) |

| footprint weight | recall |
|---|---|
| 0-0.25 | 0.016 (n=20709) |
| 0.25-0.5 | 0.020 (n=4501) |
| 0.5-0.75 | 0.005 (n=1297) |
| 0.75-1 | 0.034 (n=2591) |

| kind | all | centre cells | strong | share under 1 mm |
|---|---|---|---|---|
| combination | 0.010 (n=12428) | 0.013 (n=986) | 0.008 (n=1093) | 44.6% |
| drift | 0.007 (n=5303) | 0.005 (n=604) | 0.000 (n=152) | 77.4% |
| phantom_rain | 0.034 (n=4196) | 0.012 (n=411) | - | 77.9% |
| scale | 0.013 (n=1700) | 0.075 (n=146) | 0.033 (n=121) | 53.1% |
| spike | 0.013 (n=1212) | 0.013 (n=78) | 0.007 (n=134) | 15.5% |
| stuck | 0.036 (n=3343) | 0.012 (n=252) | 0.009 (n=340) | 51.3% |
| zeroed | 0.059 (n=916) | 0.465 (n=114) | 0.771 (n=48) | 67.1% |

Recall of the CENTRE cell, by footprint radius of its event (single cell = no neighbour is faulty):

| kind | single cell | radius 1.5-2.5 | radius 2.5-4 | radius above 4 |
|---|---|---|---|---|
| combination | 0.004 (n=529) | 0.069 (n=131) | 0.006 (n=326) | - |
| drift | 0.003 (n=316) | 0.000 (n=135) | 0.013 (n=153) | - |
| phantom_rain | 0.013 (n=234) | 0.014 (n=73) | 0.010 (n=104) | - |
| scale | 0.133 (n=75) | 0.045 (n=22) | 0.000 (n=49) | - |
| spike | 0.033 (n=30) | 0.000 (n=19) | 0.000 (n=29) | - |
| stuck | 0.008 (n=132) | 0.000 (n=58) | 0.032 (n=62) | - |
| zeroed | 0.562 (n=64) | 0.346 (n=26) | 0.333 (n=24) | - |

All cell-days, by footprint radius: single cell 0.039 (n=1380); radius 1.5-2.5 0.035 (n=5724); radius 2.5-4 0.012 (n=21994); radius above 4 -

Recall by the memory a long-memory model has at that day (history days + day of the year; a drift that starts early has little baseline):

| memory | all | drift | scale | zeroed |
|---|---|---|---|---|
| memory 90-179 d | 0.018 (n=7820) | 0.001 (n=696) | 0.111 (n=63) | 0.083 (n=24) |
| memory 180-269 d | 0.024 (n=6349) | 0.014 (n=2032) | 0.015 (n=195) | 0.063 (n=254) |
| memory 270-364 d | 0.013 (n=8434) | 0.002 (n=1990) | 0.009 (n=1391) | 0.060 (n=420) |
| memory 365+ d | 0.017 (n=6495) | 0.009 (n=585) | 0.000 (n=51) | 0.050 (n=218) |

### Ceiling check: stnet_scale_s42

SYNTHETIC faults, held-out validation years only. Budget 1 false alerts per 1,000 clean cell-days (threshold 0.112). Strong = change >= 5 mm and footprint weight >= 0.5.

Overall recall 0.191 (n=29098); recall on strong cell-days 0.307 (n=1888).
Share of fault cell-days: change under 1 mm 56.1%, weight under 0.5 86.6%, strong 6.5%.

| change (mm) | recall |
|---|---|
| 0-0.1 | 0.077 (n=6038) |
| 0.1-1 | 0.135 (n=10297) |
| 1-5 | 0.259 (n=6980) |
| 5-20 | 0.310 (n=3567) |
| 20-100 | 0.342 (n=2004) |
| 100-inf | 0.462 (n=212) |

| footprint weight | recall |
|---|---|
| 0-0.25 | 0.176 (n=20709) |
| 0.25-0.5 | 0.253 (n=4501) |
| 0.5-0.75 | 0.244 (n=1297) |
| 0.75-1 | 0.174 (n=2591) |

| kind | all | centre cells | strong | share under 1 mm |
|---|---|---|---|---|
| combination | 0.181 (n=12428) | 0.150 (n=986) | 0.224 (n=1093) | 44.6% |
| drift | 0.021 (n=5303) | 0.031 (n=604) | 0.059 (n=152) | 77.4% |
| phantom_rain | 0.127 (n=4196) | 0.153 (n=411) | - | 77.9% |
| scale | 0.059 (n=1700) | 0.247 (n=146) | 0.264 (n=121) | 53.1% |
| spike | 0.858 (n=1212) | 0.936 (n=78) | 0.925 (n=134) | 15.5% |
| stuck | 0.445 (n=3343) | 0.341 (n=252) | 0.432 (n=340) | 51.3% |
| zeroed | 0.032 (n=916) | 0.228 (n=114) | 0.458 (n=48) | 67.1% |

Recall of the CENTRE cell, by footprint radius of its event (single cell = no neighbour is faulty):

| kind | single cell | radius 1.5-2.5 | radius 2.5-4 | radius above 4 |
|---|---|---|---|---|
| combination | 0.074 (n=529) | 0.237 (n=131) | 0.239 (n=326) | - |
| drift | 0.022 (n=316) | 0.000 (n=135) | 0.078 (n=153) | - |
| phantom_rain | 0.026 (n=234) | 0.342 (n=73) | 0.308 (n=104) | - |
| scale | 0.373 (n=75) | 0.182 (n=22) | 0.082 (n=49) | - |
| spike | 0.867 (n=30) | 1.000 (n=19) | 0.966 (n=29) | - |
| stuck | 0.114 (n=132) | 0.603 (n=58) | 0.581 (n=62) | - |
| zeroed | 0.344 (n=64) | 0.038 (n=26) | 0.125 (n=24) | - |

All cell-days, by footprint radius: single cell 0.104 (n=1380); radius 1.5-2.5 0.218 (n=5724); radius 2.5-4 0.189 (n=21994); radius above 4 -

Recall by the memory a long-memory model has at that day (history days + day of the year; a drift that starts early has little baseline):

| memory | all | drift | scale | zeroed |
|---|---|---|---|---|
| memory 90-179 d | 0.252 (n=7820) | 0.006 (n=696) | 0.222 (n=63) | 0.000 (n=24) |
| memory 180-269 d | 0.204 (n=6349) | 0.038 (n=2032) | 0.133 (n=195) | 0.039 (n=254) |
| memory 270-364 d | 0.114 (n=8434) | 0.006 (n=1990) | 0.042 (n=1391) | 0.038 (n=420) |
| memory 365+ d | 0.203 (n=6495) | 0.034 (n=585) | 0.020 (n=51) | 0.014 (n=218) |

### Ceiling check: stnet_drift_s42

SYNTHETIC faults, held-out validation years only. Budget 1 false alerts per 1,000 clean cell-days (threshold 0.160). Strong = change >= 5 mm and footprint weight >= 0.5.

Overall recall 0.266 (n=29098); recall on strong cell-days 0.525 (n=1888).
Share of fault cell-days: change under 1 mm 56.1%, weight under 0.5 86.6%, strong 6.5%.

| change (mm) | recall |
|---|---|
| 0-0.1 | 0.058 (n=6038) |
| 0.1-1 | 0.153 (n=10297) |
| 1-5 | 0.301 (n=6980) |
| 5-20 | 0.568 (n=3567) |
| 20-100 | 0.755 (n=2004) |
| 100-inf | 0.821 (n=212) |

| footprint weight | recall |
|---|---|
| 0-0.25 | 0.264 (n=20709) |
| 0.25-0.5 | 0.234 (n=4501) |
| 0.5-0.75 | 0.305 (n=1297) |
| 0.75-1 | 0.317 (n=2591) |

| kind | all | centre cells | strong | share under 1 mm |
|---|---|---|---|---|
| combination | 0.499 (n=12428) | 0.489 (n=986) | 0.688 (n=1093) | 44.6% |
| drift | 0.012 (n=5303) | 0.065 (n=604) | 0.079 (n=152) | 77.4% |
| phantom_rain | 0.031 (n=4196) | 0.234 (n=411) | - | 77.9% |
| scale | 0.026 (n=1700) | 0.233 (n=146) | 0.248 (n=121) | 53.1% |
| spike | 0.558 (n=1212) | 0.769 (n=78) | 0.604 (n=134) | 15.5% |
| stuck | 0.186 (n=3343) | 0.440 (n=252) | 0.341 (n=340) | 51.3% |
| zeroed | 0.007 (n=916) | 0.000 (n=114) | 0.000 (n=48) | 67.1% |

Recall of the CENTRE cell, by footprint radius of its event (single cell = no neighbour is faulty):

| kind | single cell | radius 1.5-2.5 | radius 2.5-4 | radius above 4 |
|---|---|---|---|---|
| combination | 0.543 (n=529) | 0.275 (n=131) | 0.488 (n=326) | - |
| drift | 0.060 (n=316) | 0.037 (n=135) | 0.098 (n=153) | - |
| phantom_rain | 0.406 (n=234) | 0.014 (n=73) | 0.000 (n=104) | - |
| scale | 0.347 (n=75) | 0.227 (n=22) | 0.061 (n=49) | - |
| spike | 1.000 (n=30) | 0.895 (n=19) | 0.448 (n=29) | - |
| stuck | 0.765 (n=132) | 0.017 (n=58) | 0.145 (n=62) | - |
| zeroed | 0.000 (n=64) | 0.000 (n=26) | 0.000 (n=24) | - |

All cell-days, by footprint radius: single cell 0.404 (n=1380); radius 1.5-2.5 0.242 (n=5724); radius 2.5-4 0.264 (n=21994); radius above 4 -

Recall by the memory a long-memory model has at that day (history days + day of the year; a drift that starts early has little baseline):

| memory | all | drift | scale | zeroed |
|---|---|---|---|---|
| memory 90-179 d | 0.315 (n=7820) | 0.017 (n=696) | 0.143 (n=63) | 0.000 (n=24) |
| memory 180-269 d | 0.237 (n=6349) | 0.014 (n=2032) | 0.051 (n=195) | 0.004 (n=254) |
| memory 270-364 d | 0.115 (n=8434) | 0.007 (n=1990) | 0.018 (n=1391) | 0.010 (n=420) |
| memory 365+ d | 0.432 (n=6495) | 0.019 (n=585) | 0.020 (n=51) | 0.005 (n=218) |

### Ceiling check: stnet_l2_fault_s42

SYNTHETIC faults, held-out validation years only. Budget 1 false alerts per 1,000 clean cell-days (threshold 1.169). Strong = change >= 5 mm and footprint weight >= 0.5.

Overall recall 0.660 (n=29098); recall on strong cell-days 0.809 (n=1888).
Share of fault cell-days: change under 1 mm 56.1%, weight under 0.5 86.6%, strong 6.5%.

| change (mm) | recall |
|---|---|
| 0-0.1 | 0.484 (n=6038) |
| 0.1-1 | 0.606 (n=10297) |
| 1-5 | 0.726 (n=6980) |
| 5-20 | 0.832 (n=3567) |
| 20-100 | 0.896 (n=2004) |
| 100-inf | 0.896 (n=212) |

| footprint weight | recall |
|---|---|
| 0-0.25 | 0.658 (n=20709) |
| 0.25-0.5 | 0.662 (n=4501) |
| 0.5-0.75 | 0.795 (n=1297) |
| 0.75-1 | 0.602 (n=2591) |

| kind | all | centre cells | strong | share under 1 mm |
|---|---|---|---|---|
| combination | 0.922 (n=12428) | 0.796 (n=986) | 0.946 (n=1093) | 44.6% |
| drift | 0.021 (n=5303) | 0.063 (n=604) | 0.086 (n=152) | 77.4% |
| phantom_rain | 0.846 (n=4196) | 0.927 (n=411) | - | 77.9% |
| scale | 0.036 (n=1700) | 0.199 (n=146) | 0.198 (n=121) | 53.1% |
| spike | 0.833 (n=1212) | 0.974 (n=78) | 0.925 (n=134) | 15.5% |
| stuck | 0.888 (n=3343) | 0.893 (n=252) | 0.924 (n=340) | 51.3% |
| zeroed | 0.033 (n=916) | 0.219 (n=114) | 0.375 (n=48) | 67.1% |

Recall of the CENTRE cell, by footprint radius of its event (single cell = no neighbour is faulty):

| kind | single cell | radius 1.5-2.5 | radius 2.5-4 | radius above 4 |
|---|---|---|---|---|
| combination | 0.667 (n=529) | 0.878 (n=131) | 0.972 (n=326) | - |
| drift | 0.041 (n=316) | 0.015 (n=135) | 0.150 (n=153) | - |
| phantom_rain | 0.923 (n=234) | 0.959 (n=73) | 0.913 (n=104) | - |
| scale | 0.293 (n=75) | 0.227 (n=22) | 0.041 (n=49) | - |
| spike | 1.000 (n=30) | 1.000 (n=19) | 0.931 (n=29) | - |
| stuck | 0.848 (n=132) | 0.897 (n=58) | 0.984 (n=62) | - |
| zeroed | 0.375 (n=64) | 0.000 (n=26) | 0.042 (n=24) | - |

All cell-days, by footprint radius: single cell 0.558 (n=1380); radius 1.5-2.5 0.643 (n=5724); radius 2.5-4 0.670 (n=21994); radius above 4 -

Recall by the memory a long-memory model has at that day (history days + day of the year; a drift that starts early has little baseline):

| memory | all | drift | scale | zeroed |
|---|---|---|---|---|
| memory 90-179 d | 0.868 (n=7820) | 0.010 (n=696) | 0.381 (n=63) | 0.000 (n=24) |
| memory 180-269 d | 0.561 (n=6349) | 0.036 (n=2032) | 0.072 (n=195) | 0.039 (n=254) |
| memory 270-364 d | 0.424 (n=8434) | 0.006 (n=1990) | 0.017 (n=1391) | 0.033 (n=420) |
| memory 365+ d | 0.810 (n=6495) | 0.036 (n=585) | 0.000 (n=51) | 0.028 (n=218) |

### Ceiling check: stnet_l2_drift_s42

SYNTHETIC faults, held-out validation years only. Budget 1 false alerts per 1,000 clean cell-days (threshold 0.719). Strong = change >= 5 mm and footprint weight >= 0.5.

Overall recall 0.072 (n=29098); recall on strong cell-days 0.112 (n=1888).
Share of fault cell-days: change under 1 mm 56.1%, weight under 0.5 86.6%, strong 6.5%.

| change (mm) | recall |
|---|---|
| 0-0.1 | 0.027 (n=6038) |
| 0.1-1 | 0.061 (n=10297) |
| 1-5 | 0.092 (n=6980) |
| 5-20 | 0.117 (n=3567) |
| 20-100 | 0.103 (n=2004) |
| 100-inf | 0.179 (n=212) |

| footprint weight | recall |
|---|---|
| 0-0.25 | 0.079 (n=20709) |
| 0.25-0.5 | 0.043 (n=4501) |
| 0.5-0.75 | 0.062 (n=1297) |
| 0.75-1 | 0.072 (n=2591) |

| kind | all | centre cells | strong | share under 1 mm |
|---|---|---|---|---|
| combination | 0.160 (n=12428) | 0.129 (n=986) | 0.169 (n=1093) | 44.6% |
| drift | 0.012 (n=5303) | 0.055 (n=604) | 0.079 (n=152) | 77.4% |
| phantom_rain | 0.002 (n=4196) | 0.019 (n=411) | - | 77.9% |
| scale | 0.003 (n=1700) | 0.034 (n=146) | 0.033 (n=121) | 53.1% |
| spike | 0.002 (n=1212) | 0.000 (n=78) | 0.000 (n=134) | 15.5% |
| stuck | 0.004 (n=3343) | 0.036 (n=252) | 0.024 (n=340) | 51.3% |
| zeroed | 0.011 (n=916) | 0.035 (n=114) | 0.042 (n=48) | 67.1% |

Recall of the CENTRE cell, by footprint radius of its event (single cell = no neighbour is faulty):

| kind | single cell | radius 1.5-2.5 | radius 2.5-4 | radius above 4 |
|---|---|---|---|---|
| combination | 0.166 (n=529) | 0.130 (n=131) | 0.067 (n=326) | - |
| drift | 0.028 (n=316) | 0.074 (n=135) | 0.092 (n=153) | - |
| phantom_rain | 0.034 (n=234) | 0.000 (n=73) | 0.000 (n=104) | - |
| scale | 0.067 (n=75) | 0.000 (n=22) | 0.000 (n=49) | - |
| spike | 0.000 (n=30) | 0.000 (n=19) | 0.000 (n=29) | - |
| stuck | 0.061 (n=132) | 0.017 (n=58) | 0.000 (n=62) | - |
| zeroed | 0.062 (n=64) | 0.000 (n=26) | 0.000 (n=24) | - |

All cell-days, by footprint radius: single cell 0.088 (n=1380); radius 1.5-2.5 0.054 (n=5724); radius 2.5-4 0.075 (n=21994); radius above 4 -

Recall by the memory a long-memory model has at that day (history days + day of the year; a drift that starts early has little baseline):

| memory | all | drift | scale | zeroed |
|---|---|---|---|---|
| memory 90-179 d | 0.087 (n=7820) | 0.003 (n=696) | 0.032 (n=63) | 0.000 (n=24) |
| memory 180-269 d | 0.035 (n=6349) | 0.028 (n=2032) | 0.015 (n=195) | 0.008 (n=254) |
| memory 270-364 d | 0.019 (n=8434) | 0.002 (n=1990) | 0.000 (n=1391) | 0.014 (n=420) |
| memory 365+ d | 0.158 (n=6495) | 0.005 (n=585) | 0.000 (n=51) | 0.009 (n=218) |
