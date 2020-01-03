const webpack = require('webpack');
const _ = require('lodash');

let build_options = (opts) =>
  _.merge({
    output: {
      path: `${__dirname}/dist`,
      libraryTarget: 'amd',
    },
    devtool: 'source-map',
    resolve: {
      extensions: ['.jsx', '.js', '.scss']
    },
    module: {
      rules: [
        {
          test: /\.jsx$/,
          exclude: /node_modules/,
          use: {
            loader: "babel-loader"
          }
        },
        {
          test: /\.s?css$/,
          use: ['style-loader', 'css-loader', 'sass-loader']
        },
        {
          test: /\.svg$/,
          use: ['svg-inline-loader']
        }
      ]
    },
  }, opts);

let notebook_opts = build_options({
  entry: './src/notebook.jsx',
  output: {filename: 'notebook.js'},
  externals: {
    'jquery': 'jquery',
    'base/js/namespace': 'base/js/namespace',
    'base/js/dialog': 'base/js/dialog',
  }
});

let lab_opts = build_options({
  entry: './src/lab.jsx',
  output: {filename: 'lab.js'},
  externals: {
    '@jupyterlab/apputils': '@jupyterlab/apputils',
    '@jupyterlab/notebook': '@jupyterlab/notebook',
    '@phosphor/widgets': '@phosphor/widgets'
  }
});

module.exports = [notebook_opts, lab_opts];
