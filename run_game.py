import importlib.machinery
import sys

import main


if not any(
        main.__file__.endswith(suffix)
        for suffix in importlib.machinery.EXTENSION_SUFFIXES):
    sys.exit(
        "Módulo principal ainda não compilado. Execute "
        "`python setup.py build_ext --inplace` e tente novamente."
    )


if __name__ == "__main__":
    main.main()
