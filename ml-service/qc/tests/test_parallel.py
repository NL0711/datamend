import sys
import time

from qc.parallel import run_parallel


def py(code):
    return [sys.executable, "-c", code]


def test_outputs_are_prefixed_both_run_at_once_and_all_codes_are_returned():
    out = []
    t = time.time()
    codes = run_parallel([py("import time; print('a1'); time.sleep(1.5); print('a2')"),
                          py("import time; print('b1'); time.sleep(1.5); print('b2')")], labels=["gpu0", "gpu1"], write=out.append)
    assert codes == [0, 0] and time.time() - t < 2.8                       # 1.5 s each, run together, not one after the other
    text = "".join(out)
    assert "[gpu0] a1" in text and "[gpu0] a2" in text and "[gpu1] b1" in text and "[gpu1] b2" in text


def test_a_failure_in_one_does_not_stop_the_other():
    out = []
    codes = run_parallel([py("import sys; print('bad'); sys.exit(3)"), py("import time; time.sleep(0.5); print('still ran')")],
                         labels=["x", "y"], write=out.append)
    assert codes == [3, 0] and "[y] still ran" in "".join(out)
