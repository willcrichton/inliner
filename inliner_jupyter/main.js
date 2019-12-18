// Add rulers to codecells
define([
  'jquery',
  'base/js/namespace',
], function ($, Jupyter) {
  "use strict";

  var window = $('<div id="api-inliner"></div>');

  let call = (pysrc, wait_output) => {
    var spinner = window.find('.inline-spinner');
    return new Promise((resolve, reject) => {
      spinner.show();
      Jupyter.notebook.kernel.execute(pysrc, {
        shell: {
          reply: (reply) => {
            if (reply.content.status == 'error') {
              var trace = reply.content.traceback.join('\n');
              // https://stackoverflow.com/questions/25245716/remove-all-ansi-colors-styles-from-strings/29497680
              var trace_no_color = trace.replace(
                /[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '');
              spinner.hide();
              reject(trace_no_color);
            } else {
              if (!wait_output) {
                spinner.hide();
                resolve(reply);
              }
            }
          },
        },
        iopub: {
          output: (outp) => {
            if (wait_output) {
              spinner.hide();
              resolve(outp.content.text)
            }
          }
        }
      });
    });
  }

  let check_call = (pysrc) => call(pysrc, false);
  let check_output = (pysrc) => call(pysrc, true);

  // spinner: https://www.w3schools.com/howto/howto_css_loader.asp
  var on_config_loaded = function() {
    window.html(`
<h1 style="margin-top:0">API Inliner</h1>
<div><button class="inline-btn inline-create">Create new</button></div>
<div class="inline-spinner"></div>
<style>
.inline-btn { margin-top: 10px; }
.inline-spinner {
  position: absolute;
  display: none;
  right: 10px;
  top: 60px;
  border: 4px solid #ccc; /* Light grey */
  border-top: 4px solid #3498db; /* Blue */
  border-radius: 50%;
  width: 30px;
  height: 30px;
  animation: spin 1s linear infinite;
}
@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
    `);

    var actions = [
      'inline', 'deadcode', 'copy_propagation', 'clean_imports', 'unread_vars', 'expand_self', 'lifetimes', 'simplify_varargs', 'remove_suffixes', 'expand_tuples'
    ];

    actions.forEach((action) => {
      var action_name = action.replace('_', ' ');
      action_name = action_name.charAt(0).toUpperCase() + action_name.slice(1);

      var html = `<div><button class="inline-btn inline-${action}">${action_name}</button>`;
      window.append(html);

      window.find(`.inline-${action}`).click(() => {
        let cmd = `inliner.${action}`;
        if (action == 'deadcode') {
          cmd = `inliner.fixpoint(${cmd})`;
        } else {
          cmd = `${cmd}()`;
        };

        check_call(cmd)
          .then(() => update_cell())
          .catch((err) => {
            console.log('err', err);
          });
      });
    });

    window.css({
      position: 'absolute',
      right: '20px',
      'font-size': '18px',
      top: '130px',
      'z-index': 100,
      background: 'white',
      padding: '20px',
      border: '1px solid #777'
    });

    let update_cell = () => {
      var cell = Jupyter.notebook.get_selected_cell();
      var print = `print(inliner.make_program(comments=True))`;
      check_output(print)
        .then((src) => cell.set_text(src.trimEnd()))
        .catch((err) => console.log('err', err));
    };

    window.find('.inline-create').click(() => {
      var cell = Jupyter.notebook.get_selected_cell();
      var cell_contents = cell.get_text();

      var setup = `
from inliner import Inliner
inliner = Inliner(${JSON.stringify(cell_contents)}, ['seaborn.categorical'])`;

      check_call(setup)
        .then(() => {
          var new_cell = Jupyter.notebook.insert_cell_below();
          Jupyter.notebook.select_next();
          update_cell();
        })
        .catch((err) => {
          console.log('err', err);
        });
    });

    $('body').append(window);
  };

  var toggle_synthesizer = function() {
    window.toggle();
  }

  var load_extension = function () {

    // first, check which view we're in, in order to decide whether to load
    var conf_sect;
    if (Jupyter.notebook) {
      // we're in notebook view
      conf_sect = Jupyter.notebook.config;
    }
    else if (Jupyter.editor) {
      // we're in file-editor view
      conf_sect = Jupyter.editor.config;
    }
    else {
      // we're some other view like dashboard, terminal, etc, so bail now
      return;
    }

    Jupyter.toolbar.add_buttons_group([
      Jupyter.keyboard_manager.actions.register({
        'help': 'API Inliner',
        'icon': 'fa-bolt',
        'handler': toggle_synthesizer,
      }, 'toggle-synthesizer', 'synthesizer')
    ]);

    conf_sect.loaded
      .then(on_config_loaded)
      .catch(function on_error(reason) {
        console.warn('inliner_jupyter', 'error:', reason);
      });
  };

  var extension = {
    load_ipython_extension: load_extension
  };
  return extension;
});
