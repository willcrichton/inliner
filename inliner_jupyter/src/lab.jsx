import React from 'react';
import ReactDOM from 'react-dom';
import {
  ICommandPalette,
  MainAreaWidget,
} from '@jupyterlab/apputils';
import {
  NotebookActions
} from '@jupyterlab/notebook';
import {
  Widget
} from '@phosphor/widgets';

import {
  Inliner,
  notebook_context
} from './main';
import {
  set_env, Env
} from './env';
import {
  NotebookState
} from './state';

window.show_error = async function(state, err) {
  console.error(err);
}

class LabEnv extends Env {
  constructor(notebook, state, session) {
    super();

    this.notebook = notebook;
    this.state = state;
    this.session = session;

    this.state.current_cell = this.get_cell_id();

    this.notebook.activeCellChanged.connect(() => {
      this.state.current_cell = this.get_cell_id();
    }, this);
  }

  get_cell_id() { return this.notebook.activeCell.editor.uuid; }

  get_and_insert() {
    const before_cell = this.notebook.activeCell;
    NotebookActions.insertBelow(this.notebook);
    NotebookActions.moveDown(this.notebook);
    const after_cell = this.notebook.activeCell;

    return {
      text: before_cell.model.value.text,
      cell_id: this.get_cell_id(),
      set_cell_text: (text) => { after_cell.model.value.text = text; }
    };
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
      if (wait_output) {
        future.onIOPub = (msg) => {
          if (msg.msg_type == 'stream') {
            resolve(msg.content.text);
          } else if (msg.msg_type == 'error') {
            reject(this.format_trace(msg.content.traceback));
          }
        }
      } else {
        future.onReply = (msg) => {
          const status = msg.content.status;
          if (status == 'ok') {
            resolve();
          } else if (status == 'error') {
            reject(this.format_trace(msg.content.traceback));
          } else if (status == 'aborted') {
            resolve();
          } else {
            throw `Unknown status ${msg.status}`;
          }
        }
      }
    });
  }
}

class LabInliner extends React.Component {
  constructor(props) {
    super(props);
    this._state = new NotebookState();
    set_env(new LabEnv(props.notebook, this._state, props.session));
  }

  render() {
    return <div >
      <notebook_context.Provider value={this._state}>
        <Inliner className="inliner-lab" />
      </notebook_context.Provider>
    </div>;
  }
}

export default {
  id: 'inliner',
  autoStart: true,
  requires: [ICommandPalette],
  activate: (app, palette) => {
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
        if (!app.shell.currentWidget) {
          return;
        }

        const notebook = app.shell.currentWidget.content;
        const session = app.shell.currentWidget.session;

        app.shell.add(widget, 'right');
        app.shell.activateById(widget.id);

        ReactDOM.render(<LabInliner notebook={notebook} session={session} />,
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
