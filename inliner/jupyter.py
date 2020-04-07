from ipywidgets import DOMWidget
from traitlets import Unicode

class CodeViewer(DOMWidget):
    _model_name = Unicode('CodeViewerModel').tag(sync=True)
    _model_module = Unicode('inliner_jupyter').tag(sync=True)
    _view_name = Unicode('CodeViewerWidget').tag(sync=True)
    _view_module = Unicode('inliner_jupyter').tag(sync=True)

    code = Unicode('hello').tag(sync=True)
