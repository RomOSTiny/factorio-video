"""Windows entry point: GUI by default, optional conversion CLI for verification."""
import sys

if '--cli' in sys.argv:
    sys.argv.remove('--cli')
    from videofactorio.__main__ import main
else:
    from videofactorio.gui import main

if __name__ == '__main__':
    main()
