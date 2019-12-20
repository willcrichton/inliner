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

  async run_pass(pass) {
    let outp = await check_output(`print(${this.name}.${pass}())`);
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

export class InlineState {
  @observable cell
  @observable targets = []
  @observable target_suggestions = []

  constructor(cell, notebook_state) {
    this.cell = cell;
    this.bridge = new PythonBridge('inliner');
    this.notebook_state = notebook_state
  }

  async setup(contents) {
    await this.bridge.setup(contents);
    await this.update_cell();

    autorun(() => {
      this.bridge.sync_targets(this.targets);
    });
  }

  async update_cell() {
    let src = await this.bridge.make_program();
    this.cell.set_text(src);
  }

  async refresh_target_suggestions() {
    let suggestions = await this.bridge.target_suggestions();
    suggestions = suggestions.filter((name) =>
      this.targets.indexOf(name) == -1);
    this.target_suggestions.clear();
    this.target_suggestions.push(...suggestions);
  }

  async undo() {
    await this.bridge.undo();
    return this.update_cell();
  }

  async run_pass(pass) {
    let ret = await this.bridge.run_pass(pass);
    await this.update_cell();
    return ret;
  }

  async autoschedule() {
    this.notebook_state.show_spinner = true;

    while (true) {
      var result = await this.run_pass('inline');
      if (!result) {
        break;
      }
      await this.run_pass('deadcode');
    }

    while (true) {
      var passes = [
        'unread_vars', 'lifetimes', 'expand_self', 'copy_propagation',
        'simplify_varargs', 'expand_tuples'
      ];

      var any_pass = false;
      for (var pass of passes) {
        var change = await this.run_pass(pass);
        any_pass = any_pass || change;
      }

      if (!any_pass) {
        break;
      }
    }

    await this.run_pass('clean_imports');
    await this.run_pass('remove_suffixes');

    this.notebook_state.show_spinner = false;
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