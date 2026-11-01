import os

from setuptools import Extension, setup
from Cython.Build import cythonize


extensions = [
    Extension(
        "logistics.modules._logistics_node",
        ["logistics/modules/logistics_node.pyx"],
    ),
    Extension(
        "logistics.modules._logistics_manager",
        ["logistics/modules/logistics_manager.pyx"],
    ),
]

setup(
    name="terra-pax-logistics",
    ext_modules=cythonize(
        extensions,
        build_dir=os.environ.get("CYTHON_BUILD_DIR", "build/cython"),
        compiler_directives={"language_level": 3},
    ),
)
