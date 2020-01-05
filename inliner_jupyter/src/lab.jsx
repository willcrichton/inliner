import React from 'react';
import ReactDOM from 'react-dom';
import {
  ICommandPalette,
  MainAreaWidget,
  Dialog
} from '@jupyterlab/apputils';
import {
  NotebookActions,
  INotebookTracker
} from '@jupyterlab/notebook';
import {
  Widget
} from '@phosphor/widgets';

import {
  Inliner,
  notebook_context
} from './main';
import {
  set_env,
  Env
} from './env';
import {
  NotebookState
} from './state';

class LabEnv extends Env {
  constructor(shell, tracker, state) {
    super();

    this.shell = shell;
    this.state = state;

    this._update_notebook();
    this._update_cell_id();

    tracker.currentChanged.connect(() => {
      this._update_notebook();
    }, this);

    this.notebook.activeCellChanged.connect(() => {
      this._update_cell_id();
    }, this);
  }

  _update_notebook() {
    this.notebook = this.shell.currentWidget.content;
    this.session = this.shell.currentWidget.session;
  }

  _update_cell_id() {
    this.state.current_cell = this.notebook.activeCell.editor.uuid;
  }

  get_and_insert() {
    const before_cell = this.notebook.activeCell;
    NotebookActions.insertBelow(this.notebook);
    NotebookActions.moveDown(this.notebook);
    const after_cell = this.notebook.activeCell;

    return {
      text: before_cell.model.value.text,
      set_cell_text: (text) => {
        after_cell.model.value.text = text;
      }
    };
  }

  show_error(error) {
    let widget = new Widget();
    widget.node.innerHTML = error;

    let dialog = new Dialog({
      title: 'Inliner error',
      body: widget,
      buttons: [Dialog.okButton({
        label: 'Dismiss'
      })]
    });

    const content = dialog.node.querySelector('.jp-Dialog-content');
    content.style.maxWidth = '900px';

    return dialog.launch();
  }

  execute(pysrc, wait_output) {
    const future = this.session.kernel.requestExecute({
      code: pysrc,
      silent: false,
      store_history: false,
      user_expressions: {},
      allow_stdin: false
    });

    return new Promise((resolve, reject) => {
      let output = null;
      let error = null;
      if (wait_output) {
        future.registerMessageHook((msg) => {
          console.log('iopub', pysrc, msg);
          if (msg.msg_type == 'stream') {
            if (msg.content.name == 'stderr') {
              console.warn('stderr', msg.content.text);
              //error = msg.content.text;
            } else {
              output = msg.content.text;
            }
          } else if (msg.msg_type == 'error') {
            error = this.format_trace(msg.content.traceback);
          }
          return true;
        });
      } else {
        future.onReply = (msg) => {
          console.log('reply', pysrc, msg);
          const status = msg.content.status;
          if (status == 'error') {
            error = reject(this.format_trace(msg.content.traceback));
          }
        }
      }
      future.done.then(() => {
        if (error !== null) {
          reject(error);
        } else {
          resolve(output);
        }
      })
    });
  }
}

class LabInliner extends React.Component {
  constructor(props) {
    super(props);
    this._state = new NotebookState();
    set_env(new LabEnv(props.shell, props.tracker, this._state));
  }

  render() {
    return <div className="inliner-lab">
      <notebook_context.Provider value={this._state}>
        <Inliner />
      </notebook_context.Provider>
    </div>;
  }
}

export default {
  id: 'inliner',
  autoStart: true,
  requires: [ICommandPalette, INotebookTracker],
  activate: (app, palette, tracker) => {
    const content = new Widget();
    const widget = new MainAreaWidget({
      content
    });
    widget.id = 'inliner';
    widget.title.label = 'Inliner';
    widget.title.closable = true;

    const command = 'inliner:open';
    app.commands.addCommand(command, {
      label: 'Open Inliner',
      execute: () => {
        app.shell.add(widget, 'right');
        app.shell.activateById(widget.id);
        ReactDOM.render(
          <LabInliner shell={app.shell} tracker={tracker} />,
          content.node);
      }
    });

    app.commands.addKeyBinding({
      command,
      args: {},
      keys: ['Ctrl I'],
      selector: '.jp-Notebook'
    });

    palette.addItem({
      command,
      category: 'Inliner'
    });

    console.log('[Inliner] Extension initialized');
  }
};