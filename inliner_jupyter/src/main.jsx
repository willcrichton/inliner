import React from 'react';
import * as mobx_react from 'mobx-react';
import 'brace';
import 'brace/mode/python';
import 'brace/theme/monokai';
import AceDiff from 'ace-diff';
import Select from 'react-select';

import {
  InlineState,
  NotebookState,
  check_call
} from './state';
import {
  get_env
} from './env';

import '../css/main.scss';
import 'ace-diff/dist/ace-diff.min.css'

export const notebook_context = React.createContext(null);


let handle_error = async (operation, state, f) => {
  try {
    let ret = await f();
    return ret;
  } catch (error) {
    let last_pass = await state.last_pass();
    error = `<div>Inliner failed during operation: <code>${operation}</code><br />
The most recent pass was: <code>${last_pass}</code><br />
The Python error was:<pre>${error}</pre></div>`;
    get_env().show_error(error);
  }
}

let CreateNew = () => {
  let notebook_state = React.useContext(notebook_context);

  let on_click = async () => {
    let {
      text,
      cell_id,
      set_cell_text
    } = get_env().get_and_insert()
    let state = new InlineState(set_cell_text, notebook_state);
    await handle_error('create_new', state, () => state.setup(text));
    notebook_state.add_state(state);

    handle_error('refresh_target_suggestions', state, () => state.refresh_target_suggestions());
  };

  return <button className="btn btn-default inline-create" onClick={on_click}
                 title="New inliner cell">
    <i className="fa fa-plus" />
  </button>;
};

let Undo = mobx_react.observer(() => {
  let state = React.useContext(notebook_context).current_state;
  return <button className="btn btn-default inline-undo" title="Undo"
                 onClick={() => handle_error('undo', state, () => state.undo())}>
    <i className="fa fa-undo" />
  </button>;
});

let Targets = mobx_react.observer(() => {
  let state = React.useContext(notebook_context).current_state;

  let suggestions =
    Array.from(state.target_suggestions.entries())
    .map(([mod, meta]) => {
      return {
        label: `${mod} (${meta.use})`,
        value: mod
      }
    });

  let open_target = (path) => () => {
    check_call(`
import subprocess as sp
import shlex
sp.check_call(shlex.split("open 'file://${path}'"))
    `)
  };

  return <div>
    <div className='inline-targets'>
      {(state.targets.length > 0)
      ? state.targets.map((target) =>
        <div key={target.name}>
          <a href='#' onClick={open_target(target.path)}>{target.name}</a>
        </div>)
      : <span className='inline-targets-missing'>No inline targets added</span>}
    </div>
    <h3>
      Suggestions
      <button className="inline-refresh-targets"
              onClick={() => handle_error(
                'refresh_target_suggestions', state,
                () => state.refresh_target_suggestions())}
              title="Refresh suggestions">
        <i className="fa fa-refresh" />
      </button>
    </h3>
    <div className='inline-target-suggestions'>
      <Select
        options={suggestions}
        value=''
        styles={{menu: base => ({...base, fontFamily: '"Source Sans Pro", monospace'})}}
        placeholder='Suggestions...'
        onChange={(selected) => {
          const name = selected.value;
          const meta = state.target_suggestions.get(name);
          state.targets.push({name, ...meta});
          state.target_suggestions.delete(name);
        }} />
    </div>
  </div>;
});

let Passes = mobx_react.observer(() => {
  let state = React.useContext(notebook_context).current_state;
  const passes = [
    'inline', 'deadcode', 'copy_propagation', 'clean_imports', 'expand_self', 'lifetimes', 'simplify_varargs', 'remove_suffixes', 'expand_tuples', 'partial_eval', 'array_index'
  ];

  return <div className='inline-passes'>
    <div>
      <button className="btn btn-default"
              onClick={() => handle_error('autoschedule', state, () => state.autoschedule())}>
        Autoschedule
      </button>
    </div>
    <div>
      <button className="btn btn-default"
              onClick={() => handle_error('autoschedule_noinline', state, () => state.autoschedule_noinline())}>
        Autoschedule (no inline)
      </button>
    </div>
    {passes.map((pass) => {
      let pass_name = pass.replace('_', ' ');
      pass_name = pass_name.charAt(0).toUpperCase() + pass_name.slice(1);

      return <div key={pass}>
        <button className='btn btn-default' className="btn btn-default"
                onClick={() => handle_error(pass, state, () => state.run_pass(pass))}>
          {pass_name}
        </button>
      </div>;
    })}
  </div>;
});

let Spinner = mobx_react.observer(() => {
  let show_spinner = React.useContext(notebook_context).show_spinner;
  return show_spinner ? <div className='inline-spinner'></div> : null;
});

@mobx_react.observer
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


let DiffButton = mobx_react.observer(() => {
  const [show, setShow] = React.useState(false);
  let state = React.useContext(notebook_context).current_state;
  return <span>
    <button className='btn btn-default'
            onClick={() => setShow(!show)}
            title="Show code diff">
      <i className="fa fa-info"></i>
    </button>
    {show ? <DiffPanel state={state} /> : null}
  </span>;
});

export let Inliner = mobx_react.observer((props) => {
  let state = React.useContext(notebook_context).current_state;
  return <div className='inliner'>
    <h1>Inliner</h1>
    <CreateNew />
    <Undo />
    <DiffButton />
    {state
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
  </div>;
});