const path = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');

module.exports = (env, argv) => {
  const isProduction = argv.mode === 'production';
  
  return {
    entry: './src/index.js',
    output: {
      path: path.resolve(__dirname, 'static'),
      filename: isProduction ? 'js/[name].[contenthash].js' : 'js/bundle.js',
      clean: true,
      publicPath: '/static/'
    },
    module: {
      rules: [
        {
          test: /\.(js|jsx)$/,
          exclude: /node_modules/,
          use: {
            loader: 'babel-loader',
            options: {
              presets: ['@babel/preset-env', '@babel/preset-react']
            }
          }
        },
        {
          test: /\.css$/i,
          use: ['style-loader', 'css-loader']
        },
        {
          test: /\.(png|svg|jpg|jpeg|gif|woff|woff2|eot|ttf|otf)$/i,
          type: 'asset/resource',
          generator: {
            filename: 'assets/[name].[hash][ext]'
          }
        }
      ]
    },
    plugins: [
      new HtmlWebpackPlugin({
        template: './src/template.html',
        filename: '../templates/index.html',
        inject: 'body'
      })
    ],
    resolve: {
      extensions: ['.js', '.jsx']
    },
    devServer: {
      static: './static',
      port: 3000,
      proxy: [
        {
          context: ['/chat', '/progress', '/sessions', '/health'],
          target: 'http://localhost:8000',
          changeOrigin: true
        }
      ]
    }
  };
}; 