import sys


def excLocation() -> str:
    tb = sys.exc_info()[2]
    if tb is None:
        return "unknown location"
    return f"line {tb.tb_lineno} in file {tb.tb_frame.f_code.co_filename}"
