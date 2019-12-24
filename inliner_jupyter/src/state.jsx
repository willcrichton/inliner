import {
  observable,
  computed,
  autorun
} from 'mobx';

import {
  check_call,
  check_output
} from './utils';

class PythonBridge {
  constructor(name) {
    this.name = name;
  }

  async setup(contents) {
    let src = `
from inliner import Inliner
import json
${this.name} = Inliner(${JSON.stringify(contents)}, [], globls=globals())`;
    return check_call(src);
  }

  async make_program() {
    var print = `print(${this.name}.make_program(comments=True))`;
    let output = await check_output(print);
    return output.trimEnd();
  }

  async target_suggestions() {
    let refresh = `
import json
print(json.dumps([mod.__name__ for mod in ${this.name}.modules()]))`;
    let outp = await check_output(refresh);
    return JSON.parse(outp);
  }

  async undo() {
    return check_call(`${this.name}.undo()`);
  }

  async run_pass(pass, fixpoint = false) {
    let call = fixpoint ? `fixpoint(inliner.${pass})` : `${pass}()`;
    let outp = await check_output(`print(${this.name}.${call})`);
    outp = outp.trim();
    if (outp != 'True' && outp != 'False') {
      throw `${pass}: ${outp}`;
    }

    return outp == 'True';
  }

  async sync_targets(targets) {
    var save = `
import json
for target in json.loads('${JSON.stringify(targets)}'):
    ${this.name}.add_target(target)`;

    return check_call(save);
  }
}

let spinner = (target, name, descriptor) => {
  const original = descriptor.value;
  descriptor.value = async function(...args) {
    let toggled = !this.notebook_state.show_spinner;
    if (toggled) {
      this.notebook_state.show_spinner = true;
    }

    try {
      let ret = await original.apply(this, args);
      return ret;
    } finally {
      if (toggled) {
        this.notebook_state.show_spinner = false;
      }
    }
  }
}

export class InlineState {
  @observable cell
  @observable targets = []
  @observable target_suggestions = []
  @observable program_history = []

  constructor(cell, notebook_state) {
    this.cell = cell;
    this.bridge = new PythonBridge('inliner');
    this.notebook_state = notebook_state
  }

  @spinner
  async setup(contents) {
    await this.bridge.setup(contents);
    await this.update_cell();

    autorun(() => {
      this.bridge.sync_targets(this.targets);
    });
  }

  @spinner
  async update_cell() {
    let src = await this.bridge.make_program();
    this.cell.set_text(src);
    this.program_history.push(src);
  }

  @spinner
  async refresh_target_suggestions() {
    let suggestions = await this.bridge.target_suggestions();
    suggestions = suggestions.filter((name) =>
      this.targets.indexOf(name) == -1);
    this.target_suggestions.clear();
    this.target_suggestions.push(...suggestions);
  }

  @spinner
  async undo() {
    await this.bridge.undo();
    await this.update_cell();
    this.program_history.pop();
    this.program_history.pop();
  }

  @spinner
  async run_pass(pass, fixpoint = false) {
    let ret = await this.bridge.run_pass(pass, fixpoint);
    await this.update_cell();
    return ret;
  }

  @spinner
  async autoschedule() {
    let run_until = async (passes) => {
      while (true) {
        var any_pass = false;
        for (var pass of passes) {
          console.log(`Running ${pass}`);
          var change = await this.run_pass(pass, pass == 'deadcode');
          any_pass = any_pass || change;
          console.log(`Finished ${pass}, change: ${change}`);
        }

        if (!any_pass) {
          return;
        }
      }
    };

    let passes = [
      'inline', 'deadcode', 'copy_propagation', 'lifetimes', 'simplify_varargs', 'partial_eval', 'expand_tuples', 'clean_imports', 'array_index'
    ];

    await run_until(passes);
    await this.run_pass('expand_self');
    await run_until(passes);

    await this.run_pass('remove_suffixes');
  }
}

export class NotebookState {
  @observable states = {}
  @observable current_cell = null
  @observable show_spinner = false

  add_state(state) {
    this.states[state.cell.cell_id] = state;
  }

  @computed get current_state() {
    return this.states[this.current_cell];
  }
}