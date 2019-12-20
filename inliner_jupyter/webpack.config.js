module.exports = {
  entry: './src/main.jsx',
  output: {
    path: `${__dirname}/dist`,
    libraryTarget: 'amd',
    filename: 'bundle.js',
  },
  devtool: 'source-map',
  resolve: {
    extensions: ['.jsx', '.js', '.scss']
  },
  module: {
    rules: [{
        test: /\.jsx$/,
        exclude: /node_modules/,
        use: {
          loader: "babel-loader"
        }
      },
      {
        test: /\.s?css$/,
        use: ['style-loader', 'css-loader', 'sass-loader']
      }
    ]
  },
  externals: {
    'jquery': 'jquery',
    'base/js/namespace': 'base/js/namespace',
    'base/js/dialog': 'base/js/dialog'
  }
}