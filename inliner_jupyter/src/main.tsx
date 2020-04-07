import React from 'react';
import * as mobx_react from 'mobx-react';
import * as mobx from 'mobx';
import 'brace';
import 'brace/mode/python';
import 'brace/theme/monokai';
import AceDiff from 'ace-diff';
import Select, { OptionTypeBase } from 'react-select';
import _ from 'lodash';
import localStorage from 'mobx-localstorage';
import Jupyter from 'base/js/namespace';

import {
  InlineState,
  NotebookState,
  check_call,
  Target
} from './state';
import {
  get_env
} from './env';

import '../css/main.scss';
import 'ace-diff/dist/ace-diff.min.css';

export const notebook_context = React.createContext<NotebookState|null>(null);

let dev_mode = () => localStorage.getItem('INLINER_DEV_MODE');
let toggle_dev_mode = () => localStorage.setItem('INLINER_DEV_MODE', !dev_mode());


let handle_error = async (operation: string, state: InlineState, f: () => void) => {
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
  let notebook_state = React.useContext(notebook_context)!;

  let on_click = async () => {
    let {
      text,
      cell_id,
      methods
    } = get_env().get_and_insert()
    let state = new InlineState(methods, notebook_state);
    await handle_error('create_new', state, () => state.setup(text));
    notebook_state.add_state(state);

    await handle_error('refresh_target_suggestions',
                       state, () => state.refresh_target_suggestions());
  };

  return <div>
    <div>Select a code cell and click the button below to start inlining.</div>
    <button className="btn btn-default inline-create" onClick={on_click}
            title="New inliner cell"
            style={{marginTop: '5px'}}>
      Create inliner cell
    </button>
  </div>;
};

let UndoButton = mobx_react.observer(() => {
  let state = React.useContext(notebook_context)!.current_state;
  return <button className="btn btn-default inline-undo" title="Undo"
                 onClick={() => handle_error('undo', state, () => state.undo())}>
    <i className="fa fa-undo" />
  </button>;
});

let Targets = mobx_react.observer(() => {
  let state = React.useContext(notebook_context)!.current_state;

  let module_blacklist = ['matplotlib', 'pandas', 'numpy'];

  let suggestions =
    Array
      .from(state ? state.target_suggestions.entries() : [])
      .filter(([mod, meta]) => {
        if (!dev_mode()) {
          const base = mod.split('.')[0];
          return !module_blacklist.includes(base);
        } else {
          return true;
        }
      })
      .map(([mod, meta]) => {
        return {
          label: `${mod} (${meta.use})`,
          value: mod
        }
      });
  suggestions = _.sortBy(suggestions, (s) => s.label);

  let open_target = (path: string) => () => {
    check_call(`
import subprocess as sp
import shlex
sp.check_call(shlex.split("open 'file://${path}'"))
    `)
  };

  let remove_target = (target: Target) => () => {
    state.targets.remove(target);
    state.refresh_target_suggestions();
  };

  let select_ref: any | null = null;

  return <div>
    <div className='inline-targets'>
      {(state && state.targets.length > 0)
        ? state.targets.map((target: Target) =>
          <div key={target.name}>
            <a href='#' onClick={open_target(target.path)}>{target.name}</a>
            <button className='btn btn-default' onClick={remove_target(target)}>
              <i className='fa fa-minus' />
            </button>
          </div>)
        : <span className='inline-targets-missing'>No inline targets added</span>}
    </div>
    <h3>
      <button className="inline-refresh-targets"
              onClick={() => handle_error(
                'refresh_target_suggestions', state,
                async () => {
                  await state.refresh_target_suggestions();
                  select_ref!.select.openMenu();
                  select_ref!.focus();
                })}
              title="Refresh suggestions">
        <i className="fa fa-refresh" />
      </button>
      <button className=''
              onClick={async () => {
                const text = get_env().get_selected_text();
                const path = await state.get_object_path(text);
                state.targets.push({name: path, path: text, use: ""});
              }}>
        <i className='fa fa-copy' />
      </button>
    </h3>
    <div className='inline-target-suggestions'
         data-intro="Pick at least one module that you want to inline"
         data-step="3"
         data-position="top">
      <Select
        ref={(n) => { 
          if (n instanceof Select) { select_ref = n; }}
        }
        options={suggestions}
        value={{label: '', value: ''}}
        styles={{menu: base => ({
          ...base,
          fontFamily: '"Source Sans Pro", monospace',
          width: '400px',
          right: 0})}}
        placeholder='Suggestions...'
        onChange={(selected) => {
          const name: string = select_ref!.value;
          const meta = state.target_suggestions.get(name);
          state.targets.push({name, ...meta});
          state.target_suggestions.delete(name);
        }} />
    </div>
    <div className='inline-target-add'>
      <input placeholder='Add a target...'
             onFocus={() => { Jupyter.keyboard_manager.disable() }}
             onBlur={() => { Jupyter.keyboard_manager.enable() }}
             onKeyDown={(e) => {
               if (e.target instanceof HTMLInputElement && e.key === 'Enter') {
                  const input = e.target;
                  state.targets.push({name: input.value, path: "", use: ""});
                  input.value = '';
                  input.blur();
               }
             }} />
    </div>
  </div>;
});

let Passes = mobx_react.observer(() => {
  let state = React.useContext(notebook_context)!.current_state;

  const passes = [
    'inline', 'dead_code', 'copy_propagation', 'clean_imports', 'record_to_vars', 'unused_vars', 'remove_suffixes'
  ];

  return <div className='inline-passes'>
    <div>
      <button className='btn btn-default'
              onClick={async () => {
                await handle_error('inline', state, () => {
                  const cursor = get_env().get_cursor_pos();
                  if (cursor === null) {
                    throw "You must click on the function in the code cell that you want to inline.";
                  }
                  state.inline(cursor);
                });
              }}>
        Inline
      </button>
    </div>
    <div>
      <button className="btn btn-default"
              data-intro="Click 'Optimize' to inline and clean code from the inline targets"
              data-step="4"
              onClick={async () => {
                await handle_error('optimize', state, () => state.optimize());
              }}>
        Optimize
      </button>
    </div>
    {dev_mode()
      ? passes.map((pass) => {
        let pass_name = pass.replace('_', ' ');
        pass_name = pass_name.charAt(0).toUpperCase() + pass_name.slice(1);
        return <div key={pass}>
          <button className='btn btn-default'
                  onClick={() => handle_error(pass, state, async () => {
                    const change = await state.run_pass(pass);
                    console.log('Change:', change);
                  })}>
            {pass_name}
          </button>
        </div>;
      })
      : null}
  </div>;
});

let Spinner = mobx_react.observer(() => {
  let show_spinner = React.useContext(notebook_context)!.show_spinner;
  return show_spinner ? <div className='inline-spinner'></div> : null;
});

@mobx_react.observer
class DiffPanel extends React.Component<{state: InlineState}> {
  diff: AceDiff | null = null
  _el: HTMLElement | null = null

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
          element: this._el!,
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

    return <div className='inline-diff-panel' ref={(el) => {
      if (el instanceof HTMLElement) {
        this._el = el;
      }
    }}>
    </div>;
  }
}


let DiffButton = mobx_react.observer(() => {
  const [show, setShow] = React.useState(false);
  let state = React.useContext(notebook_context)!.current_state;
  return <span>
    <button className='btn btn-default'
            onClick={() => setShow(!show)}
            title="Show code diff">
      <i className="fa fa-exchange"></i>
    </button>
    {show ? <DiffPanel state={state} /> : null}
  </span>;
});

let BugButton = mobx_react.observer(() => {
  let state = React.useContext(notebook_context)!.current_state;
  let debug = async () => {
    const prog = await state.debug();
    get_env().create_new_cell(prog);
  };
  return <span>
    <button className='btn btn-default' onClick={debug} title='Debug'>
      <i className='fa fa-bug' />
    </button>
  </span>
});

let DevButton = mobx_react.observer(() => {
  return <span className={`dev-button ${dev_mode() ? "active": ""}`}
               onClick={toggle_dev_mode}>
    <i className='fa fa-gears' />
  </span>;
});

let FoldButton = mobx_react.observer(() => {
  let state = React.useContext(notebook_context)!.current_state;
  return <span>
    <button className='btn btn-default' title='Fold code'
            onClick={() => state.fold_code()}>
      <i className='fa fa-folder-open-o' />
    </button>
  </span>;
});

export class Inliner extends React.Component {
  render() {
    return <notebook_context.Consumer>{(state) =>
        <mobx_react.Observer>{() =>
          <div className='inliner'>
            <h1>
              Inliner
            </h1>
            <DevButton />
            {state!.current_state
              ? <div>
                <div>
                  <UndoButton />
                  <DiffButton />
                  <FoldButton />
                  {dev_mode()
                    ? <span>
                      <BugButton />
                    </span> : null}
                </div>
                <hr />
                <div>
                  <h2>Passes</h2>
                  <Passes />
                </div>
                <hr />
                <div>
                  <h2>Targets</h2>
                  <Targets />
                </div>
              </div>
              : <CreateNewButton />}
            <Spinner />
          </div>
        }</mobx_react.Observer>}
      </notebook_context.Consumer>;
  }
}
