from utils import run_optimize_harness
from pytest import mark


@mark.last
def test_stress_json():
    import json

    def prog():
        assert json.dumps({}) == '{}'

    outp = '''
from _json import make_encoder as c_make_encoder
from json import _default_encoder
from json.encoder import (INFINITY, JSONEncoder, _make_iterencode,
                          encode_basestring, encode_basestring_ascii)
obj___dumps = {}
"""Serialize ``obj`` to a JSON formatted ``str``."""
# cached encoder
"""Return a JSON string representation of a Python data structure."""
# This is for extremely simple cases and benchmarks.
    # This doesn't pass the iterator directly to ''.join() because the
    # exceptions aren't as detailed.  The list call should be roughly
    # equivalent to the PySequence_Fast that ''.join() would do.
"""Encode the given object and yield each string"""
markers = {}

_iterencode = c_make_encoder(
    markers, _default_encoder.default, encode_basestring_ascii, _default_encoder.indent,
    _default_encoder.key_separator, _default_encoder.item_separator, _default_encoder.sort_keys,
    _default_encoder.skipkeys, _default_encoder.allow_nan)
iterencode_ret = _iterencode(obj___dumps, 0)
encode_ret = ''.join(iterencode_ret)
assert encode_ret == '{}'
'''

    run_optimize_harness(prog, json, outp, locals())


@mark.last
def test_stress_seaborn_boxplot():
    import seaborn as sns
    import seaborn.categorical
    tips = sns.load_dataset('tips')

    def prog():
        sns.boxplot(x=tips.day, y=tips.tip)

    outp = '''import colorsys

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
"""Convert input specification into a common representation."""

# Option 2:
# We are plotting a long-form dataset
# -----------------------------------

# See if we need to get variables from `data`

# Validate the inputs

        # Figure out the plotting orientation
"""Determine how the plot should be oriented based on the data."""
orient___establish_variables = str(orient___establish_variables)

infer_orient_ret = "v"

orient___establish_variables = infer_orient_ret

# Option 2b:
# We are grouping the data values by another variable
# ---------------------------------------------------

# Determine which role each variable will play
vals, groups = y___boxplot, x___boxplot

# Get the categorical axis label
group_label = groups.name

# Get the order on the categorical axis
group_names = categorical_order(groups, None)

# Group the numeric data
"""Group a long-form variable by another with correct order."""
# Ensure that the groupby will work

# Group the val data
grouped_vals = vals.groupby(groups)
out_data = []
for g in group_names:
    g_vals = grouped_vals.get_group(g)
    out_data.append(g_vals)

# Get the vals axis label
label = vals.name

_group_longform_ret = out_data, label
plot_data, value_label = _group_longform_ret

# Now handle the hue levels for nested ordering

# Now handle the units for nested observations

    # Assign object attributes
    # ------------------------
"""Get a list of colors for the main component of the plots."""
n_colors = len(plot_data)

# Determine the main colors
# Determine whether the current palette will have enough values
# If not, we'll default to the husl palette so each is distinct
current_palette = utils.get_color_cycle()
colors = color_palette(n_colors=n_colors)

# Desaturate a bit because these are patches
colors = color_palette(colors, desat=saturation___boxplot)

# Convert the colors to a common representations
rgb_colors = color_palette(colors)

# Determine the gray color to use for the lines framing the plot
light_vals = [colorsys.rgb_to_hls(*c)[1] for c in rgb_colors]
lum = min(light_vals) * .6
gray = mpl.colors.rgb2hex((lum, lum, lum))

# Assign object attributes

linewidth___boxplot = mpl.rcParams["lines.linewidth"]

ax___boxplot = plt.gca()
kwargs___boxplot.update(dict(whis=whis___boxplot))

"""Make the plot."""
"""Use matplotlib to draw a boxplot on an Axes."""
vert = orient___establish_variables == "v"

props = {}
for obj in ["box", "whisker", "cap", "median", "flier"]:
    props[obj] = kwargs___boxplot.pop(obj + "props", {})

for i, group_data in enumerate(plot_data):

    # Handle case where there is data at this level

    # Draw a single box or a set of boxes
    # with a single level of grouping
    box_data = np.asarray(remove_na(group_data))

    # Handle case where there is no non-null data

    artist_dict = ax___boxplot.boxplot(box_data,
                             vert=vert,
                             patch_artist=True,
                             positions=[i],
                             widths=width___boxplot,
                             **kwargs___boxplot)
    color = rgb_colors[i]
    """Take a drawn matplotlib boxplot and make it look nice."""
    for box in artist_dict["boxes"]:
        box.update(dict(facecolor=color,
                        zorder=.9,
                        edgecolor=gray,
                        linewidth=linewidth___boxplot))
        box.update(props["box"])
    for whisk in artist_dict["whiskers"]:
        whisk.update(dict(color=gray,
                          linewidth=linewidth___boxplot,
                          linestyle="-"))
        whisk.update(props["whisker"])
    for cap in artist_dict["caps"]:
        cap.update(dict(color=gray,
                        linewidth=linewidth___boxplot))
        cap.update(props["cap"])
    for med in artist_dict["medians"]:
        med.update(dict(color=gray,
                        linewidth=linewidth___boxplot))
        med.update(props["median"])
    for fly in artist_dict["fliers"]:
        fly.update(dict(markerfacecolor=gray,
                        marker="d",
                        markeredgecolor=gray,
                        markersize=fliersize___boxplot))
        fly.update(props["flier"])
"""Add descriptive labels to an Axes object."""
xlabel, ylabel = group_label, value_label

ax___boxplot.set_xlabel(xlabel)
ax___boxplot.set_ylabel(ylabel)

ax___boxplot.set_xticks(np.arange(len(plot_data)))
ax___boxplot.set_xticklabels(group_names)

ax___boxplot.xaxis.grid(False)
ax___boxplot.set_xlim(-.5, len(plot_data) - .5, auto=None)'''

    run_optimize_harness(prog, seaborn.categorical, outp, locals())
