import os
from pathlib import Path

from setuptools import Extension, setup
from Cython.Build import cythonize


ROOT = Path(__file__).parent
PACKAGE_DIRS = (
    "controllers",
    "graphics",
    "players",
    "ui",
    "logistics",
    "logistics/modules",
)
DEVELOPMENT_MODULES = {"check_textures.py", "validate_game.py"}
PYX_FALLBACKS = {
    "logistics/modules/logistics_manager.py",
    "logistics/modules/logistics_node.py",
}
COMPILE_ARGS = ["/O2"] if os.name == "nt" else ["-O3"]

python_modules = [
    ROOT / filename
    for filename in ("main.py", "game_state.py")
]
for package_dir in PACKAGE_DIRS:
    python_modules.extend(
        source
        for source in (ROOT / package_dir).glob("*.py")
        if source.name != "__init__.py"
        and source.name not in DEVELOPMENT_MODULES
        and source.relative_to(ROOT).as_posix() not in PYX_FALLBACKS
    )

extensions = [
    Extension(
        ".".join(source.relative_to(ROOT).with_suffix("").parts),
        [str(source.relative_to(ROOT))],
        extra_compile_args=COMPILE_ARGS,
    )
    for source in sorted(python_modules)
] + [
    Extension(
        "logistics.modules._logistics_node",
        ["logistics/modules/logistics_node.pyx"],
        extra_compile_args=COMPILE_ARGS,
    ),
    Extension(
        "logistics.modules._logistics_manager",
        ["logistics/modules/logistics_manager.pyx"],
        extra_compile_args=COMPILE_ARGS,
    ),
]

setup(
    name="terra-pax",
    ext_modules=cythonize(
        extensions,
        build_dir=os.environ.get("CYTHON_BUILD_DIR", "build/cython"),
        compiler_directives={"language_level": 3},
    ),
)
