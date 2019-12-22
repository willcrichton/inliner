import Jupyter from 'base/js/namespace';
import React, {
  useState
} from 'react';
import ReactDOM from 'react-dom';
import {
  observer
} from 'mobx-react';

import 'brace';
import 'brace/mode/python';
import 'brace/theme/monokai';
import AceDiff from 'ace-diff';


import {
  InlineState,
  NotebookState
} from './state';

import '../css/main.scss';
import 'ace-diff/dist/ace-diff.min.css'

const DEV_MODE = true;

const notebook_context = React.createContext(null);

let CreateNew = () => {
  let notebook_state = React.useContext(notebook_context);

  let on_click = async () => {
    let cell = Jupyter.notebook.get_selected_cell();

    let new_cell = Jupyter.notebook.insert_cell_below();
    Jupyter.notebook.select_next();
    notebook_state.current_cell = new_cell.cell_id;

    let state = new InlineState(new_cell, notebook_state);
    await state.setup(cell.get_text());
    notebook_state.add_state(state);

    state.refresh_target_suggestions();
  };

  return <button className="inline-btn inline-create" onClick={on_click}>
    <i className="fa fa-plus"></i>
  </button>;
};

let Undo = observer(() => {
  let state = React.useContext(notebook_context).current_state;
  return <button className="inline-btn inline-undo" onClick={() => state.undo()}>
    <i className="fa fa-undo"></i>
  </button>;
});

let Targets = observer(() => {
  let state = React.useContext(notebook_context).current_state;
  return <div>
    <div className='inline-targets'>
      {state.targets.length > 0
                            ? state.targets.map((name) => <div key={name}>- {name}</div>)
                            : <span className='inline-targets-missing'>No inline targets added</span>}
    </div>
    <h3>Suggestions <button className="inline-refresh-targets"
                            onClick={state.refresh_target_suggestions.bind(state)}>
      <i className="fa fa-refresh"></i>
    </button></h3>
    <div className='inline-target-suggestions'>
      {state.target_suggestions.map((name) => {
        let on_click = () => {
          state.targets.push(name);
          state.target_suggestions.splice(
            state.target_suggestions.indexOf(name), 1);
        };
        return <button key={name} onClick={on_click}>{name}</button>;
      })}
    </div>
  </div>;
});

let Passes = observer(() => {
  let state = React.useContext(notebook_context).current_state;
  const passes = [
    'inline', 'deadcode', 'copy_propagation', 'clean_imports', 'unread_vars', 'expand_self', 'lifetimes', 'simplify_varargs', 'remove_suffixes', 'expand_tuples'
  ];

  return <div className='inline-passes'>
    <div>
      <button className="inline-btn inline-autoschedule"
              onClick={() => state.autoschedule()}>
        Autoschedule
      </button>
    </div>
    {passes.map((pass) => {
      let pass_name = pass.replace('_', ' ');
      pass_name = pass_name.charAt(0).toUpperCase() + pass_name.slice(1);

      let on_click = () => {
        state.run_pass(pass);
      };

      return <div key={pass}><button className="inline-btn" onClick={on_click}>
        {pass_name}
      </button></div>;
    })}
  </div>;
});

let Spinner = observer(() => {
  let show_spinner = React.useContext(notebook_context).show_spinner;
  return show_spinner ? <div className='inline-spinner'></div> : null;
});

@observer
class DiffPanel extends React.Component {
  componentDidMount() {
    this._set_diff();
  }

  componentDidUpdate() {
    this._set_diff();
  }

  _set_diff() {
    let state = this.props.state;
    if (state) {
      let hist_len = state.program_history.length;
      if (hist_len >= 2) {
        let before = state.program_history[hist_len - 2];
        let after = state.program_history[hist_len - 1];

        if (this.diff) {
          this.diff.destroy();
        }

        this.diff = new AceDiff({
          element: this._el,
          mode: 'ace/mode/python',
          left: {
            content: before,
            copyLinkEnabled: false,
            editable: false
          },
          right: {
            content: after,
            copyLinkEnabled: false,
            editable: false
          }
        });
      }
    }
  }

  componentWillUnmount() {
    if (this.diff) {
      this.diff.destroy();
    }
  }

  render() {
    let state = this.props.state;
    if (state) {
      // HACK: have to observe program_history here for the _set_diff callback
      // to register with mobx
      state.program_history.length;
    }

    return <div className='inline-diff-panel' ref={(el) => {this._el = el}}>
    </div>;
  }
}


let DiffButton = observer(() => {
  const [show, setShow] = useState(false);
  let state = React.useContext(notebook_context).current_state;
  return <span>
    <button onClick={() => setShow(!show)}>
      <i className="fa fa-info"></i>
    </button>
    {show ? <DiffPanel state={state} /> : null}
  </span>;
});

@observer
class Inliner extends React.Component {
  state = {
    show: DEV_MODE,
  }

  constructor(props) {
    super(props);
    this._state = new NotebookState();
  }

  componentDidMount() {
    let toggle_show = () => {
      this.setState({
        show: !this.state.show
      })
    };

    Jupyter.toolbar.add_buttons_group([
      Jupyter.keyboard_manager.actions.register({
        'help': 'Inliner',
        'icon': 'fa-bolt',
        'handler': toggle_show,
      }, 'toggle-inliner', 'inliner')
    ]);

    let update_current_cell = () => {
      let cell = Jupyter.notebook.get_selected_cell();
      this._state.current_cell = cell.cell_id;
    }

    // https://github.com/jupyter/notebook/blob/76a323e677b7080a1e9a88437d6b5cea6cc0403b/notebook/static/notebook/js/notebook.js#L332
    ['select.Cell', 'set_dirty.Notebook'].forEach((event) => {
      Jupyter.notebook.events.on(event, () => update_current_cell());
    });
  }

  render() {
    let style = {
      display: this.state.show ? 'block' : 'none'
    };

    return <div className='inliner' style={style}>
      <notebook_context.Provider value={this._state}>
        <h1>Inliner</h1>
        <CreateNew />
        <Undo />
        <DiffButton />
        {this._state.current_state
        ? <div>
          <hr />
          <div>
            <h2>Targets</h2>
            <Targets />
          </div>
          <hr />
          <div>
            <h2>Passes</h2>
            <Passes />
          </div>
        </div>
        : null}
        <Spinner />
      </notebook_context.Provider>
    </div>;
  }
}

export async function load_ipython_extension() {
  console.warn('RUNNING!');

  await Jupyter.notebook.config.loaded;

  let container = document.createElement('div');
  document.body.appendChild(container);

  ReactDOM.render(<Inliner />, container);
};