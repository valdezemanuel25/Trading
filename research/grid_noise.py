import itertools
import numpy as np, pandas as pd
from panel import load_panel, period_mask, TRAIN, VALID, POINT, COST
from noise import run, sigma_table

d = load_panel(); days = d["days"]
tr, va = period_mask(days, TRAIN), period_mask(days, VALID)
sigs = {lb: sigma_table(d, lb) for lb in (10, 14, 20)}

def stats(p, t, m):
    net = p[m] * POINT - t[m] * COST
    return net.sum(), net.mean() / net.std() * np.sqrt(252), p[m].sum() / max(t[m].sum(), 1), t[m].sum()

rows = []
for lb, step, mult, first in itertools.product((10, 14, 20), (30, 60), (0.75, 1.0, 1.5, 2.0), (30, 60)):
    p, t = run(d, lookback=lb, step=step, mult=mult, first=first, sig=sigs[lb])
    a, b = stats(p, t, tr), stats(p, t, va)
    rows.append(dict(lb=lb, step=step, mult=mult, first=first, train_net=round(a[0]), train_sh=round(a[1], 2),
                     train_pts=round(a[2], 2), train_n=a[3], valid_net=round(b[0]), valid_sh=round(b[1], 2),
                     valid_pts=round(b[2], 2)))
g = pd.DataFrame(rows).sort_values("train_sh", ascending=False)
pd.set_option("display.width", 200)
print(g.to_string(index=False))
