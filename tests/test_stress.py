from utils import run_optimize_harness
from pytest import mark


@mark.last
def test_stress_json():
    import json

    def prog():
        assert json.dumps({}) == '{}'

    outp = '''from _json import make_encoder as c_make_encoder
from json import _default_encoder
from json.encoder import (INFINITY, JSONEncoder, _make_iterencode,
                          encode_basestring, encode_basestring_ascii)
obj = {}
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
iterencode_ret = _iterencode(obj, 0)
encode_ret = ''.join(iterencode_ret)
assert encode_ret == '{}'
'''

    run_optimize_harness(prog, json, outp, locals())


@mark.last
def test_stress_seaborn_boxplot():
    import seaborn as sns
    import seaborn.categorical
    import matplotlib.pyplot as plt
    tips = sns.load_dataset('tips')

    # Silence warnings from repeatedly opening plots
    plt.rcParams.update({'figure.max_open_warning': 0})

    def prog():
        sns.boxplot(x=tips.day, y=tips.tip)

    outp = '''import colorsys

import matplotlib as mpl
import numpy as np
import pandas as pd
from seaborn import utils
from seaborn.categorical import _BoxPlotter, _CategoricalPlotter
from seaborn.palettes import (color_palette, dark_palette, husl_palette,
                              light_palette)
from seaborn.utils import categorical_order, remove_na

saturation = .75
width = .8
fliersize = 5
whis = 1.5
kwargs = {}

orient = None
"""Convert input specification into a common representation."""

# Option 2:
# We are plotting a long-form dataset
# -----------------------------------

# See if we need to get variables from `data`

# Validate the inputs

        # Figure out the plotting orientation
orient_2 = orient
"""Determine how the plot should be oriented based on the data."""
orient_2 = str(orient_2)

infer_orient_ret = "v"

orient = infer_orient_ret

# Option 2b:
# We are grouping the data values by another variable
# ---------------------------------------------------

# Determine which role each variable will play
vals, groups = tips.tip, tips.day

# Get the categorical axis label

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

_group_longform_ret = out_data, vals.name
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
colors = color_palette(colors, desat=saturation)

# Convert the colors to a common representations
rgb_colors = color_palette(colors)

# Determine the gray color to use for the lines framing the plot
light_vals = [colorsys.rgb_to_hls(*c)[1] for c in rgb_colors]
lum = min(light_vals) * .6
gray = mpl.colors.rgb2hex((lum, lum, lum))

# Assign object attributes

linewidth = mpl.rcParams["lines.linewidth"]

ax = plt.gca()
kwargs.update(dict(whis=whis))

"""Make the plot."""
"""Use matplotlib to draw a boxplot on an Axes."""
vert = orient == "v"

props = {}
for obj in ["box", "whisker", "cap", "median", "flier"]:
    props[obj] = kwargs.pop(obj + "props", {})

for i, group_data in enumerate(plot_data):

    # Handle case where there is data at this level

    # Draw a single box or a set of boxes
    # with a single level of grouping
    box_data = np.asarray(remove_na(group_data))

    # Handle case where there is no non-null data

    artist_dict = ax.boxplot(box_data,
                             vert=vert,
                             patch_artist=True,
                             positions=[i],
                             widths=width,
                             **kwargs)
    color = rgb_colors[i]
    """Take a drawn matplotlib boxplot and make it look nice."""
    for box in artist_dict["boxes"]:
        box.update(dict(facecolor=color,
                        zorder=.9,
                        edgecolor=gray,
                        linewidth=linewidth))
        box.update(props["box"])
    for whisk in artist_dict["whiskers"]:
        whisk.update(dict(color=gray,
                          linewidth=linewidth,
                          linestyle="-"))
        whisk.update(props["whisker"])
    for cap in artist_dict["caps"]:
        cap.update(dict(color=gray,
                        linewidth=linewidth))
        cap.update(props["cap"])
    for med in artist_dict["medians"]:
        med.update(dict(color=gray,
                        linewidth=linewidth))
        med.update(props["median"])
    for fly in artist_dict["fliers"]:
        fly.update(dict(markerfacecolor=gray,
                        marker="d",
                        markeredgecolor=gray,
                        markersize=fliersize))
        fly.update(props["flier"])
"""Add descriptive labels to an Axes object."""
xlabel, ylabel = groups.name, value_label

ax.set_xlabel(xlabel)
ax.set_ylabel(ylabel)

ax.set_xticks(np.arange(len(plot_data)))
ax.set_xticklabels(group_names)

ax.xaxis.grid(False)
ax.set_xlim(-.5, len(plot_data) - .5, auto=None)'''

    run_optimize_harness(prog, seaborn.categorical, outp, locals())


@mark.last
def test_stress_seaborn_facetgrid():
    import seaborn as sns
    import seaborn.axisgrid
    import matplotlib.pyplot as plt
    tips = sns.load_dataset('tips')

    # Silence warnings from repeatedly opening plots
    plt.rcParams.update({'figure.max_open_warning': 0})

    def prog():
        g = sns.FacetGrid(data=tips, row='sex', col='day')
        g.map(plt.hist, 'tip')

    outp = '''import warnings
from distutils.version import LooseVersion
from itertools import product

import matplotlib as mpl
import numpy as np
from seaborn import utils
from seaborn.axisgrid import FacetGrid, Grid
from seaborn.palettes import color_palette

row = 'sex'
col = 'day'
height = 3
aspect = 1
hue_kws = None
subplot_kws = None
gridspec_kws = None

MPL_GRIDSPEC_VERSION = LooseVersion('1.4')
OLD_MPL = LooseVersion(mpl.__version__) < MPL_GRIDSPEC_VERSION

# Handle deprecations

# Determine the hue facet layer information

"""Get a list of colors for the hue variable."""
palette = color_palette(n_colors=1)

row_names = utils.categorical_order(tips[row], None)
col_names = utils.categorical_order(tips[col], None)

# Additional dict of kwarg -> list of values for mapping the hue var
hue_kws = hue_kws if hue_kws is not None else {}

# Make a boolean mask that is True anywhere there is an NA
# value in one of the faceting variables, but only if dropna is True
none_na = np.zeros(len(tips), np.bool)
row_na = none_na if row is None else tips[row].isnull()
col_na = none_na if col is None else tips[col].isnull()
hue_na = none_na if None is None else tips[None].isnull()
not_na = ~(row_na | col_na | hue_na)

# Compute the grid shape
ncol = 1 if col is None else len(col_names)
nrow = 1 if row is None else len(row_names)

# Calculate the base figure size
# This can get stretched later by a legend
# TODO this doesn't account for axis labels
figsize = (ncol * height * aspect, nrow * height)

# Validate some inputs

# Build the subplot keyword dictionary
subplot_kws = {} if subplot_kws is None else subplot_kws.copy()
gridspec_kws = {} if gridspec_kws is None else gridspec_kws.copy()

# Initialize the subplot grid
kwargs = dict(figsize=figsize, squeeze=False,
              sharex=True, sharey=True,
              subplot_kw=subplot_kws,
              gridspec_kw=gridspec_kws)

fig, axes = plt.subplots(nrow, ncol, **kwargs)

    # Set up the class attributes
    # ---------------------------

    # First the public API

# Next the private variables

_legend_data = {}

# Make the axes look good
fig.tight_layout()
kwargs = {}
"""Remove axis spines from the facets."""
utils.despine(fig, **kwargs)
args = ['tip']
kwargs_2 = {}
"""Apply a plotting function to each facet's subset of the data."""
# If color was a keyword argument, grab it here
kw_color = kwargs_2.pop("color", None)

func_module = str(plt.hist.__module__)

# Check for categorical plots without order information

    # Iterate over the data subsets
facet_data_ret = []
"""Generator for name indices and data subsets for each facet."""

# Construct masks for the row variable
row_masks = [tips[row] == n for n in row_names]

# Construct masks for the column variable
col_masks = [tips[col] == n for n in col_names]
hue_masks = [np.repeat(True, len(tips))]

# Here is the main generator loop
for (i, row), (j, col), (k, hue) in product(enumerate(row_masks),
                                            enumerate(col_masks),
                                            enumerate(hue_masks)):
    data_ijk = tips[row & col & hue & not_na]
    facet_data_ret.append(((i, j, k), data_ijk))
for (row_i, col_j, hue_k), data_ijk in facet_data_ret:

    # If this subset is null, move on

    # Get the current axis
    """Make the axis identified by these indices active and return it."""
    ax = axes[row_i, col_j]

    # Get a reference to the axes object we want, and make it active
    plt.sca(ax)
    ax = ax

    # Decide what color to plot with

    color = palette[hue_k]
    kwargs_2["color"] = color

    # Insert the other hue aesthetics if appropriate

    # Insert a label in the keyword arguments for the legend

    # Get the actual data we are going to plot with
    plot_data = data_ijk[list(args)]
    plot_data = plot_data.dropna()
    plot_args = [v for k, v in plot_data.iteritems()]

    # Some matplotlib functions don't handle pandas objects correctly
    plot_args = [v.values for v in plot_args]

    # Draw the plot

    # Draw the plot
    plt.hist(*plot_args, **kwargs_2)

    # Sort out the supporting information
    """Extract the legend data from an axes object and save it."""
    handles, labels = ax.get_legend_handles_labels()
    data = {l: h for h, l in zip(handles, labels)}
    _legend_data.update(data)
    """Turn off axis labels and legend."""
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.legend_ = None

# Finalize the annotations and layout
axlabels = args[:2]
"""Finalize the annotations and layout."""
x_var = axlabels[0]
"""Set axis labels on the left column and bottom row of the grid."""
kwargs_3 = {}
"""Label the x axis on the bottom row of the grid."""
"""Return a flat array of the bottom row of axes."""
_bottom_axes = axes[-1, :].flat
for ax in _bottom_axes:
    ax.set_xlabel(x_var, **kwargs_3)
kwargs_4 = {}
"""Draw titles either above each facet or on the grid margins."""
args = dict(row_var=row, col_var=col)
kwargs_4["size"] = kwargs_4.pop("size", mpl.rcParams["axes.labelsize"])

# Establish default templates
row_template = "{row_var} = {row_name}"
col_template = "{col_var} = {col_name}"
template = " | ".join([row_template, col_template])

row_template = utils.to_utf8(row_template)
col_template = utils.to_utf8(col_template)
template = utils.to_utf8(template)

# Otherwise title each facet with all the necessary information
for i, row_name in enumerate(row_names):
    for j, col_name in enumerate(col_names):
        args.update(dict(row_name=row_name, col_name=col_name))
        title = template.format(**args)
        axes[i, j].set_title(title, **kwargs_4)
fig.tight_layout()'''

    run_optimize_harness(prog, seaborn.axisgrid, outp, locals())
