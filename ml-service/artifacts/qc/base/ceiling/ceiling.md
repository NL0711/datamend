### Ceiling check: fusion_logistic_s42

SYNTHETIC faults, held-out validation years only. Budget 1 false alerts per 1,000 clean cell-days (threshold -1.509). Strong = change >= 5 mm and footprint weight >= 0.5.

Overall recall 0.436 (n=29098); recall on strong cell-days 0.678 (n=1888).
Share of fault cell-days: change under 1 mm 56.1%, weight under 0.5 86.6%, strong 6.5%.

| change (mm) | recall |
|---|---|
| 0-0.1 | 0.378 (n=6038) |
| 0.1-1 | 0.400 (n=10297) |
| 1-5 | 0.418 (n=6980) |
| 5-20 | 0.488 (n=3567) |
| 20-100 | 0.705 (n=2004) |
| 100-inf | 0.976 (n=212) |

| footprint weight | recall |
|---|---|
| 0-0.25 | 0.415 (n=20709) |
| 0.25-0.5 | 0.439 (n=4501) |
| 0.5-0.75 | 0.570 (n=1297) |
| 0.75-1 | 0.530 (n=2591) |

| kind | all | centre cells | strong | share under 1 mm |
|---|---|---|---|---|
| combination | 0.502 (n=12428) | 0.660 (n=986) | 0.732 (n=1093) | 44.6% |
| drift | 0.009 (n=5303) | 0.051 (n=604) | 0.066 (n=152) | 77.4% |
| phantom_rain | 0.787 (n=4196) | 0.805 (n=411) | - | 77.9% |
| scale | 0.030 (n=1700) | 0.267 (n=146) | 0.289 (n=121) | 53.1% |
| spike | 0.223 (n=1212) | 0.962 (n=78) | 0.828 (n=134) | 15.5% |
| stuck | 0.826 (n=3343) | 0.968 (n=252) | 0.953 (n=340) | 51.3% |
| zeroed | 0.004 (n=916) | 0.009 (n=114) | 0.000 (n=48) | 67.1% |

### Ceiling check: fusion_boosted_s42

SYNTHETIC faults, held-out validation years only. Budget 1 false alerts per 1,000 clean cell-days (threshold -2.632). Strong = change >= 5 mm and footprint weight >= 0.5.

Overall recall 0.470 (n=29098); recall on strong cell-days 0.709 (n=1888).
Share of fault cell-days: change under 1 mm 56.1%, weight under 0.5 86.6%, strong 6.5%.

| change (mm) | recall |
|---|---|
| 0-0.1 | 0.372 (n=6038) |
| 0.1-1 | 0.415 (n=10297) |
| 1-5 | 0.490 (n=6980) |
| 5-20 | 0.589 (n=3567) |
| 20-100 | 0.718 (n=2004) |
| 100-inf | 0.920 (n=212) |

| footprint weight | recall |
|---|---|
| 0-0.25 | 0.443 (n=20709) |
| 0.25-0.5 | 0.514 (n=4501) |
| 0.5-0.75 | 0.621 (n=1297) |
| 0.75-1 | 0.530 (n=2591) |

| kind | all | centre cells | strong | share under 1 mm |
|---|---|---|---|---|
| combination | 0.591 (n=12428) | 0.697 (n=986) | 0.822 (n=1093) | 44.6% |
| drift | 0.006 (n=5303) | 0.025 (n=604) | 0.033 (n=152) | 77.4% |
| phantom_rain | 0.783 (n=4196) | 0.808 (n=411) | - | 77.9% |
| scale | 0.021 (n=1700) | 0.171 (n=146) | 0.190 (n=121) | 53.1% |
| spike | 0.216 (n=1212) | 0.795 (n=78) | 0.664 (n=134) | 15.5% |
| stuck | 0.809 (n=3343) | 0.968 (n=252) | 0.935 (n=340) | 51.3% |
| zeroed | 0.012 (n=916) | 0.079 (n=114) | 0.104 (n=48) | 67.1% |

### Ceiling check: rules

SYNTHETIC faults, held-out validation years only. Budget 1 false alerts per 1,000 clean cell-days (threshold 0.378). Strong = change >= 5 mm and footprint weight >= 0.5.

Overall recall 0.429 (n=29098); recall on strong cell-days 0.631 (n=1888).
Share of fault cell-days: change under 1 mm 56.1%, weight under 0.5 86.6%, strong 6.5%.

| change (mm) | recall |
|---|---|
| 0-0.1 | 0.381 (n=6038) |
| 0.1-1 | 0.399 (n=10297) |
| 1-5 | 0.404 (n=6980) |
| 5-20 | 0.470 (n=3567) |
| 20-100 | 0.687 (n=2004) |
| 100-inf | 0.934 (n=212) |

| footprint weight | recall |
|---|---|
| 0-0.25 | 0.414 (n=20709) |
| 0.25-0.5 | 0.433 (n=4501) |
| 0.5-0.75 | 0.563 (n=1297) |
| 0.75-1 | 0.469 (n=2591) |

| kind | all | centre cells | strong | share under 1 mm |
|---|---|---|---|---|
| combination | 0.495 (n=12428) | 0.573 (n=986) | 0.686 (n=1093) | 44.6% |
| drift | 0.001 (n=5303) | 0.005 (n=604) | 0.007 (n=152) | 77.4% |
| phantom_rain | 0.786 (n=4196) | 0.783 (n=411) | - | 77.9% |
| scale | 0.015 (n=1700) | 0.123 (n=146) | 0.157 (n=121) | 53.1% |
| spike | 0.201 (n=1212) | 0.821 (n=78) | 0.724 (n=134) | 15.5% |
| stuck | 0.824 (n=3343) | 0.968 (n=252) | 0.953 (n=340) | 51.3% |
| zeroed | 0.001 (n=916) | 0.000 (n=114) | 0.000 (n=48) | 67.1% |
