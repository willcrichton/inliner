// Add rulers to codecells
define([
  'jquery',
  'base/js/namespace',
], function ($, Jupyter) {
  "use strict";

  var widget = $('<div id="api-inliner"></div>');

  let format_trace = (reply) => {
    var trace = reply.content.traceback.join('\n');
    // https://stackoverflow.com/questions/25245716/remove-all-ansi-colors-styles-from-strings/29497680
    var trace_no_color = trace.replace(
      /[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '');
    return trace_no_color;
  };

  let call = (pysrc, wait_output) => {
    var spinner = widget.find('.inline-spinner');
    return new Promise((resolve, reject) => {
      spinner.show();
      Jupyter.notebook.kernel.execute(pysrc, {
        shell: {
          reply: (reply) => {
            if (!wait_output) {
              spinner.hide();
              if (reply.content.status == 'error') {
                reject(format_trace(reply));
              } else {
                resolve(reply);
              }
            }
          },
        },
        iopub: {
          output: (reply) => {
            if (wait_output) {
              spinner.hide();
              if (reply.msg_type == 'error') {
                reject(format_trace(reply));
              } else {
                // HACK: if a call both prints to stdout and raises
                // an exception, then the iopub.output callback receives
                // two messages, and the stdout comes before the error.
                // We can wait a little bit to see if we get the error first
                // before resolving.
                setTimeout(() => {
                  resolve(reply.content.text)
                }, 100);
              }
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
    widget.html(`
<h1 style="margin-top:0">API Inliner</h1>
<div><button class="inline-btn inline-create">Create new</button></div>
<div><button class="inline-btn inline-undo">Undo</button></div>
<div><button class="inline-btn inline-autoschedule">Autoschedule</button></div>
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
      widget.append(html);

      widget.find(`.inline-${action}`).click(() => {
        let cmd = `inliner.${action}`;
        if (action == 'deadcode') {
          cmd = `inliner.fixpoint(${cmd})`;
        } else {
          cmd = `${cmd}()`;
        };

        check_call(cmd)
          .then(() => update_cell())
          .catch((err) => {
            console.error(err);
          });
      });
    });

    widget.css({
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
      return check_output(print)
        .then((src) => cell.set_text(src.trimEnd()));
    };

    window.inliner = {update_cell: update_cell};

    widget.find('.inline-create').click(() => {
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
          console.error(err);
        });
    });

    widget.find('.inline-undo').click(() => {
      check_call('inliner.undo()').then(() => update_cell());
    });

    widget.find('.inline-autoschedule').click(() => {
      async function run(pass) {
        var change = await check_output(`print(inliner.${pass}())`)
          .then((outp) => {
            outp = outp.trim();
            if (outp != 'True' && outp != 'False') {
              throw new Error(`${pass}: ${outp}`);
            }

            return outp == 'True';
          });
        await update_cell();
        return change;
      }

      async function test() {
        while (true) {
          var result = await run('inline');
          if (!result) {
            break;
          }
          await run('deadcode');
        }

        while (true) {
          var passes = [
            'expand_self', 'unread_vars', 'lifetimes', 'copy_propagation',
            'simplify_varargs', 'expand_tuples'
          ];

          var any_pass = false;
          for (var pass of passes) {
            var change = await run(pass);
            any_pass = any_pass || change;
          }

          if (!any_pass) {
            break;
          }
        }

        await run('clean_imports');
        await run('remove_suffixes');
      }

      test()
        .catch((err) => {
          console.error(err);
        });
    });

    $('body').append(widget);
  };

  var toggle_synthesizer = function() {
    widget.toggle();
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
