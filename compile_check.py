import glob, py_compile, sys
bad=0
for f in glob.glob("*.py"):
    try:
        py_compile.compile(f, doraise=True)
        print("OK", f)
    except Exception as e:
        print("BAD", f, e)
        bad += 1
sys.exit(bad)
