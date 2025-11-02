# Temporary shim for Python 3.13 where stdlib 'cgi' was removed.
# Provides parse_header() used by older libs.

from email.parser import Parser

def parse_header(line: str):
    # Build a fake header so email.parser can do the work
    msg = Parser().parsestr(f"Content-Type: {line}\n\n")
    main = msg.get_content_type()
    # get_params returns list of tuples: [(key, val), ...] including first being main type
    params_list = msg.get_params()
    params = {}
    if params_list:
        # skip the first which is the main content-type
        for k, v in params_list[1:]:
            params[k] = v
    return main, params
