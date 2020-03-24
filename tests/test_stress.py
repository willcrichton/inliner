from utils import run_optimize_harness


def test_stress_json():
    import json

    def prog():
        assert json.dumps({}) == '{}'

    # yapf: disable
    def outp():
        from _json import make_encoder as c_make_encoder
        from json import _default_encoder
        from json.encoder import (INFINITY, JSONEncoder, _make_iterencode,
                                  encode_basestring, encode_basestring_ascii)
        obj___dumps = {}
        markers = {}
        _iterencode = c_make_encoder(
            markers, _default_encoder.default, encode_basestring_ascii, _default_encoder.indent,
            _default_encoder.key_separator, _default_encoder.item_separator, _default_encoder.sort_keys,
            _default_encoder.skipkeys, _default_encoder.allow_nan)
        iterencode_ret = _iterencode(obj___dumps, 0)
        encode_ret = ''.join(iterencode_ret)
        assert encode_ret == '{}'

    run_optimize_harness(prog, json, outp, locals())


def test_stress_seaborn_boxplot():
    import seaborn as sns
    import seaborn.categorical
    tips = sns.load_dataset('tips')

    def prog():
        sns.boxplot(x=tips.day, y=tips.tip)

    outp = """import colorsys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from seaborn import utils
from seaborn.categorical import _BoxPlotter, _CategoricalPlotter
from seaborn.palettes import (color_palette, dark_palette, husl_palette,
                              light_palette)
from seaborn.utils import categorical_order, remove_na
x___boxplot = tips.day
y___boxplot = tips.tip
saturation___boxplot = .75
width___boxplot = .8
fliersize___boxplot = 5
whis___boxplot = 1.5
kwargs___boxplot = {}
orient___establish_variables = None
orient___establish_variables = str(orient___establish_variables)
infer_orient_ret = "v"

        # Figure out the plotting orientation
orient___establish_variables = infer_orient_ret
vals, groups = y___boxplot, x___boxplot
group_label = groups.name

# Get the order on the categorical axis
group_names = categorical_order(groups, None)

# Group the val data
grouped_vals = vals.groupby(groups)
out_data = []
for g in group_names:
    g_vals = grouped_vals.get_group(g)
    out_data.append(g_vals)

# Get the vals axis label
label = vals.name
_group_longform_ret = out_data, label

# Group the numeric data
plot_data, value_label = _group_longform_ret
n_colors = len(plot_data)
# Determine whether the current palette will have enough values
# If not, we'll default to the husl palette so each is distinct
current_palette = utils.get_color_cycle()
colors = color_palette(n_colors=n_colors)
colors = color_palette(colors, desat=saturation___boxplot)

# Convert the colors to a common representations
rgb_colors = color_palette(colors)

# Determine the gray color to use for the lines framing the plot
light_vals = [colorsys.rgb_to_hls(*c)[1] for c in rgb_colors]
lum = min(light_vals) * .6
gray = mpl.colors.rgb2hex((lum, lum, lum))
linewidth_____init__ = mpl.rcParams["lines.linewidth"]
ax___boxplot = plt.gca()
kwargs___boxplot.update(dict(whis=whis___boxplot))
vert = orient___establish_variables == "v"

props = {}
for obj in ["box", "whisker", "cap", "median", "flier"]:
    props[obj] = kwargs___boxplot.pop(obj + "props", {})

for i, group_data in enumerate(plot_data):

    # Draw a single box or a set of boxes
    # with a single level of grouping
    box_data = np.asarray(remove_na(group_data))

    artist_dict = ax___boxplot.boxplot(box_data,
                             vert=vert,
                             patch_artist=True,
                             positions=[i],
                             widths=width___boxplot,
                             **kwargs___boxplot)
    color = rgb_colors[i]
    for box in artist_dict["boxes"]:
        box.update(dict(facecolor=color,
                        zorder=.9,
                        edgecolor=gray,
                        linewidth=linewidth_____init__))
        box.update(props["box"])
    for whisk in artist_dict["whiskers"]:
        whisk.update(dict(color=gray,
                          linewidth=linewidth_____init__,
                          linestyle="-"))
        whisk.update(props["whisker"])
    for cap in artist_dict["caps"]:
        cap.update(dict(color=gray,
                        linewidth=linewidth_____init__))
        cap.update(props["cap"])
    for med in artist_dict["medians"]:
        med.update(dict(color=gray,
                        linewidth=linewidth_____init__))
        med.update(props["median"])
    for fly in artist_dict["fliers"]:
        fly.update(dict(markerfacecolor=gray,
                        marker="d",
                        markeredgecolor=gray,
                        markersize=fliersize___boxplot))
        fly.update(props["flier"])
xlabel, ylabel = group_label, value_label
ax___boxplot.set_xlabel(xlabel)
ax___boxplot.set_ylabel(ylabel)
ax___boxplot.set_xticks(np.arange(len(plot_data)))
ax___boxplot.set_xticklabels(group_names)
ax___boxplot.xaxis.grid(False)
ax___boxplot.set_xlim(-.5, len(plot_data) - .5, auto=None)"""

    run_optimize_harness(prog, seaborn.categorical, outp, locals())
