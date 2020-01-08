import React from 'react';
import * as mobx_react from 'mobx-react';
import 'brace';
import 'brace/mode/python';
import 'brace/theme/monokai';
import AceDiff from 'ace-diff';
import Select from 'react-select';
import _ from 'lodash';
import introJs from 'intro.js';

import {
  InlineState,
  NotebookState,
  check_call
} from './state';
import {
  get_env
} from './env';

import '../css/main.scss';
import 'ace-diff/dist/ace-diff.min.css';
import 'intro.js/introjs.css';

export const notebook_context = React.createContext(null);
const intro_context = React.createContext(null);

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

let CreateNewButton = () => {
  let notebook_state = React.useContext(notebook_context);
  let intro = React.useContext(intro_context);

  let on_click = async () => {
    let {
      text,
      cell_id,
      set_cell_text
    } = get_env().get_and_insert()
    let state = new InlineState(set_cell_text, notebook_state);
    await handle_error('create_new', state, () => state.setup(text));
    notebook_state.add_state(state);

    await handle_error('refresh_target_suggestions', state, () => state.refresh_target_suggestions());

    intro.nextStep();
  };

  return <button className="btn btn-default inline-create" onClick={on_click}
                 title="New inliner cell"
                 data-intro="Click on the notebook cell you want to expand, then click on this button to create an inliner cell"
                 data-step="2">
    <i className="fa fa-plus" />
  </button>;
};

let UndoButton = mobx_react.observer(() => {
  let state = React.useContext(notebook_context).current_state;
  return <button className="btn btn-default inline-undo" title="Undo"
                 onClick={() => handle_error('undo', state, () => state.undo())}>
    <i className="fa fa-undo" />
  </button>;
});

let Targets = mobx_react.observer(() => {
  let state = React.useContext(notebook_context).current_state;
  let intro = React.useContext(intro_context);

  let suggestions =
    Array.from(state ? state.target_suggestions.entries() : [])
    .map(([mod, meta]) => {
      return {
        label: `${mod} (${meta.use})`,
        value: mod
      }
    });
  suggestions = _.sortBy(suggestions, (s) => s.label);

  let open_target = (path) => () => {
    check_call(`
import subprocess as sp
import shlex
sp.check_call(shlex.split("open 'file://${path}'"))
    `)
  };

  let select_ref = null;

  return <div>
    <div className='inline-targets'>
      {(state && state.targets.length > 0)
      ? state.targets.map((target) =>
        <div key={target.name}>
          <a href='#' onClick={open_target(target.path)}>{target.name}</a>
        </div>)
      : <span className='inline-targets-missing'>No inline targets added</span>}
    </div>
    <h3>
      Suggestions &nbsp;
      <button className="inline-refresh-targets"
              data-intro="Once you've completed inlining, click here to refresh the set of possible modules to inline"
              data-step="5"
              onClick={() => handle_error(
                'refresh_target_suggestions', state,
                async () => {
                  await state.refresh_target_suggestions();
                  select_ref.select.openMenu();
                  select_ref.focus();
                  intro.nextStep();
                })}
              title="Refresh suggestions">
        <i className="fa fa-refresh" />
      </button>
    </h3>
    <div className='inline-target-suggestions'
         data-intro="Pick at least one module that you want to inline"
         data-step="3"
         data-position="top">
      <Select
        ref={(n) => { if (n !== null) { select_ref = n; }}}
        options={suggestions}
        value=''
        styles={{menu: base => ({
          ...base,
          fontFamily: '"Source Sans Pro", monospace',
          width: '400px',
          right: 0})}}
        placeholder='Suggestions...'
        onChange={(selected) => {
          const name = selected.value;
          const meta = state.target_suggestions.get(name);
          state.targets.push({name, ...meta});
          state.target_suggestions.delete(name);
          intro.nextStep();
        }} />
    </div>
  </div>;
});

let Passes = mobx_react.observer(() => {
  let state = React.useContext(notebook_context).current_state;
  let intro = React.useContext(intro_context)

  const passes = [
    'inline', 'deadcode', 'copy_propagation', 'clean_imports', 'expand_self', 'lifetimes', 'simplify_varargs', 'remove_suffixes', 'expand_tuples', 'partial_eval', 'array_index'
  ];

  return <div className='inline-passes'>
    <div>
      <button className="btn btn-default"
              data-intro="Click 'Simplify' to inline and clean code from the inline targets"
              data-step="4"
              onClick={async () => {
                await handle_error('simplify', state, () => state.simplify());
                intro.nextStep();
              }}>
        Simplify
      </button>
    </div>
    <div>
      <button className="btn btn-default"
              onClick={() => handle_error('simplify_noinline', state, () => state.simplify_noinline())}>
        Simplify (no inline)
      </button>
    </div>
    {passes.map((pass) => {
      let pass_name = pass.replace('_', ' ');
      pass_name = pass_name.charAt(0).toUpperCase() + pass_name.slice(1);

      return <div key={pass}>
        <button data-intro={pass_name == 'inline' ?
                            'You can run passes individually, like inlining' : null}
                data-step="6"
                className='btn btn-default' className="btn btn-default"
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
      <i className="fa fa-exchange"></i>
    </button>
    {show ? <DiffPanel state={state} /> : null}
  </span>;
});

let TutorialButton = () => {
  let intro = React.useContext(intro_context);
  return <span>
    <button className='btn btn-default'
            onClick={() => intro.start()}
            title='Tutorial'>
      <i className='fa fa-info' />
    </button>
  </span>;
};

export class Inliner extends React.Component {
  state = {
    intro: null
  }

  componentDidMount() {
    this.setState({
      intro: introJs()
    });
  }

  render() {
    return <intro_context.Provider value={this.state.intro}>
      <notebook_context.Consumer>{(state) =>
        <mobx_react.Observer>{() =>
          <div className='inliner'>
            <h1
              data-intro="This tutorial will show explain how the inlining tool works."
              data-step="1">
              Inliner
            </h1>
            <span>
              <CreateNewButton />
              <UndoButton />
              <DiffButton />
              <TutorialButton />
            </span>
            <div style={{display: state.current_state ? 'block' : 'none'}}>
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
            <Spinner />
          </div>
        }</mobx_react.Observer>}
      </notebook_context.Consumer>
    </intro_context.Provider>;
  }
}