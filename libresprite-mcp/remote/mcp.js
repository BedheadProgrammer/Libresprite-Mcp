/**
 * LibreSprite MCP Remote Script
 *
 * This script runs inside LibreSprite and acts as a bridge between the
 * MCP server's relay endpoint and LibreSprite's JavaScript scripting engine.
 *
 * It polls the relay server for scripts to execute and posts the output back.
 *
 * Setup: Copy this file to LibreSprite's scripts folder, then run it from
 * the Scripts menu inside LibreSprite.
 *
 * Source: https://github.com/BedheadProgrammer/Libresprite-Mcp
 */

// Cache the global context.
var global = this;

/**
 * MCP Remote Script — IIFE to avoid global namespace pollution.
 */
(function MCP() {
    // CONSTANTS //

    /**
     * URL to the relay server.
     */
    var RELAY_SERVER_URL = 'http://localhost:64823';

    /**
     * Delay between polling requests (in rendering cycles).
     */
    var POLL_DELAY = 120;


    // VARIABLES //

    /**
     * Flag indicating extension state.
     * @type {boolean}
     */
    var active = false;

    /**
     * Flag indicating whether polling is active.
     * @type {boolean}
     */
    var polling = false;

    /**
     * Flag indicating whether the client is connected to the server.
     * @type {boolean}
     */
    var connected = false;

    /**
     * Stores stdout captured from script execution.
     * @type {string}
     */
    var output = '';

    /**
     * Function to handle GET response in the next cycle.
     * @type {Function|null}
     */
    var _get_response = null;

    /**
     * Function to handle POST response in the next cycle.
     * @type {Function|null}
     */
    var _post_response = null;

    /**
     * Dialog instance for UI.
     */
    var dialog = null;


    // FUNCTIONS //

    /**
     * Original console.log reference.
     */
    var _clientLogger = global.console.log;

    // Create a custom console object that captures output.
    var console = {};
    for (var key in global.console) {
        console[key] = global.console[key];
    }

    /**
     * Modified console.log that captures output before logging.
     */
    console.log = function() {
        var args = Array.prototype.slice.call(arguments);
        output += args.join(' ') + '\n';
        _clientLogger.apply(null, args);
    };

    /**
     * Makes a GET request using LibreSprite's storage.fetch.
     *
     * @param {string} url - URL to fetch
     * @param {Function} cb - Callback function(response)
     */
    function _get(url, cb) {
        storage.fetch(url, '_get_response');
        _get_response = function() {
            var status = storage.get('_get_response' + '_status');
            var string = storage.get('_get_response');
            cb({
                string: string,
                status: status
            });
        };
    }

    /**
     * Makes a POST request using LibreSprite's storage.fetch.
     *
     * @param {string} url - URL to fetch
     * @param {string} body - Request body (JSON string)
     * @param {Function} cb - Callback function(response)
     */
    function _post(url, body, cb) {
        storage.fetch(url, '_post_response', '', 'POST', body, 'Content-Type', 'application/json');
        _post_response = function() {
            var status = storage.get('_post_response' + '_status');
            var string = storage.get('_post_response');
            cb({
                string: string,
                status: status
            });
        };
    }

    /**
     * Makes a GET request and parses JSON response.
     *
     * @param {string} url - URL to fetch
     * @param {Function} cb - Callback(data, error)
     */
    function get(url, cb) {
        _get(url, function(rsp) {
            var data, error = rsp.status !== 200 ? 'status:' + rsp.status : 0;
            try {
                if (!error)
                    data = JSON.parse(rsp.string);
            } catch (ex) {
                error = ex;
            }
            cb(data, error);
        });
    }

    /**
     * Makes a POST request and parses JSON response.
     *
     * @param {string} url - URL to fetch
     * @param {string} body - JSON string body
     * @param {Function} cb - Callback(data, error)
     */
    function post(url, body, cb) {
        _post(url, body, function(rsp) {
            var data, error = rsp.status !== 200 ? 'status:' + rsp.status : 0;
            try {
                if (!error)
                    data = JSON.parse(rsp.string);
                else
                    error += rsp.string;
            } catch (ex) {
                error = ex;
            }
            cb(data, error);
        });
    }

    /**
     * Pings the relay server for health.
     */
    function checkServerHealth() {
        get(RELAY_SERVER_URL + '/ping', function(data, error) {
            if (error) {
                connected = false;
                app.yield('bad_health', POLL_DELAY);
                return;
            }
            if (data && data.status === 'pong') {
                connected = true;
                app.yield('good_health');
            } else {
                connected = false;
                app.yield('bad_health', POLL_DELAY);
            }
        });
    }

    /**
     * Fetches the next script from the relay server.
     *
     * @param {Function} cb - Script handler callback(script)
     */
    function getScript(cb) {
        get(RELAY_SERVER_URL, function(data, error) {
            if (error) {
                cb('');
                return;
            }
            cb((data && data.script) ? data.script : '');
        });
    }

    /**
     * Posts the captured output back to the relay server.
     */
    function postOutput() {
        var body = JSON.stringify({output: output});
        post(RELAY_SERVER_URL, body, function(data, error) {
            if (error) {
                _clientLogger('The MCP server was shut down.');
                connected = false;
                paintUI();
                app.yield('bad_health', POLL_DELAY);
                return;
            }
            if (!data) {
                _clientLogger('Something went wrong. Please report it on https://github.com/BedheadProgrammer/Libresprite-Mcp/issues.');
                return;
            }
            if (data.status === 'invalid') {
                _clientLogger('Something is wrong. Please report it on https://github.com/BedheadProgrammer/Libresprite-Mcp/issues.');
            }
            // Continue polling...
            if (!polling) {
                return;
            }
            app.yield('poll', POLL_DELAY);
        });
    }

    /**
     * Runs a script in the current LibreSprite context.
     *
     * @param {string} script - JavaScript code to execute
     */
    function runScript(script) {
        if (!script) {
            return;
        }
        try {
            new Function('console', script)(console);
        } catch (e) {
            console.log('Error in script:', e.message);
        }
    }

    /**
     * Fetch, execute, and post output for the next script.
     * Entry point for the polling loop.
     */
    function exec() {
        if (!polling) return;
        getScript(function(script) {
            output = '';
            runScript(script);
            postOutput();
        });
    }

    /**
     * Start the polling loop.
     */
    function startPolling() {
        if (polling) return;
        polling = true;
        exec();
    }

    /**
     * Stop the polling loop.
     */
    function stopPolling() {
        polling = false;
    }

    /**
     * Paint the UI dialog based on connection state.
     */
    function paintUI() {
        var label;
        if (!connected) {
            label = 'Discovering MCP servers... Make sure the libresprite-mcp server is running.';
        } else if (polling) {
            label = 'Connected to the libresprite-mcp server!';
        } else {
            label = 'Found an active libresprite-mcp server, click "Connect" when ready!';
        }
        if (dialog) {
            dialog.close();
        }
        dialog = app.createDialog();
        dialog.title = 'libresprite-mcp';
        dialog.addLabel(label);
        dialog.addBreak();
        dialog.canClose = !connected || !polling;
        if (connected) {
            dialog.addButton(
                polling ? 'Disconnect' : 'Connect',
                'toggle'
            );
        }
    }


    // EVENT HANDLER //

    /**
     * Global event handler for LibreSprite script events.
     *
     * @param {string} event - The event name
     */
    function onEvent(event) {
        switch (event) {
            case 'init':
                active = true;
                checkServerHealth();
                paintUI();
                return;

            case '_close':
                active = false;
                connected = false;
                polling = false;
                return;

            case 'bad_health':
                if (!active) return;
                checkServerHealth();
                return;

            case 'good_health':
                paintUI();
                return;

            case 'toggle_click':
                if (polling) {
                    stopPolling();
                } else {
                    startPolling();
                }
                paintUI();
                return;

            case '_get_response_fetch':
                if (_get_response) _get_response();
                _get_response = null;
                return;

            case '_post_response_fetch':
                if (_post_response) _post_response();
                _post_response = null;
                return;

            case 'poll':
                if (!active) {
                    stopPolling();
                    return;
                }
                exec();
                return;

            default:
                break;
        }
    }
    global.onEvent = onEvent;
})();
