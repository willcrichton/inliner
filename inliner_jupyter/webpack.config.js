const CopyWebpackPlugin = require('copy-webpack-plugin')
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
      extensions: ['.ts', '.tsx', '.jsx', '.js', '.scss', '.wasm']
    },
    module: {
      rules: [
        {
          test: /\.tsx?$/,
          loader: 'ts-loader'
        },
        {
          test: /\.s?css$/,
          use: ['style-loader', 'css-loader', 'sass-loader']
        },
        {
          test: /\.svg$/,
          use: ['svg-inline-loader']
        },
      ]
    },
    plugins: [
      new webpack.IgnorePlugin({resourceRegExp: /^fs$/}),
      new CopyWebpackPlugin([{from: 'src/tree-sitter'}])
    ]
  }, opts);

let notebook_opts = build_options({
  entry: './src/notebook.tsx',
  output: {filename: 'notebook.js'},
  externals: {
    'jquery': 'jquery',
    'base/js/namespace': 'base/js/namespace',
    'base/js/dialog': 'base/js/dialog',
    'codemirror/lib/codemirror': 'codemirror/lib/codemirror',
  }
});

let lab_opts = build_options({
  entry: './src/lab.tsx',
  output: {filename: 'lab.js'},
  externals: {
    '@jupyterlab/apputils': '@jupyterlab/apputils',
    '@jupyterlab/notebook': '@jupyterlab/notebook',
    '@phosphor/widgets': '@phosphor/widgets'
  }
});

module.exports = [notebook_opts] //lab_opts
