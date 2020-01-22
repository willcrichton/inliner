from setuptools import setup, find_packages

if __name__ == "__main__":
    setup(name='inliner',
          version='0.3.11',
          description='Human-readable inlining of Python code',
          url='http://github.com/willcrichton/inliner',
          author='Will Crichton',
          author_email='wcrichto@cs.stanford.edu',
          license='Apache 2.0',
          packages=find_packages(),
          install_requires=[
              'astor', 'iterextras', 'numpy', 'pandas', 'astpretty'
          ],
          data_files=[('share/jupyter/nbextensions/inliner', [
              'inliner_jupyter/dist/notebook.js',
              'inliner_jupyter/dist/notebook.js.map',
          ]),
                      ('etc/jupyter/nbconfig/notebook.d',
                       ['inliner_jupyter/inliner.json'])],
          setup_requires=['pytest-runner'],
          tests_require=['pytest', 'seaborn'],
          zip_safe=False)
