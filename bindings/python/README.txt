//===----------------------------------------------------------------------===//
// Clang Python Bindings
//===----------------------------------------------------------------------===//

This directory implements Python bindings for Clang.

The Python bindings currently implement every feature of libclang except
for the high-level indexing API.

Using
=====

The Python bindings are written in pure Python. However, they make use
of the Python ctypes module to call into the libclang shared library.

For the Python part, you will need the "clang" directory from where this
file is contained to be in your PYTHONPATH or sys.path from within
Python itself. Typically you will copy these directories to a system or
user path.

For the libclang part, Python will need to be able to find the shared
library. If libclang.so is not in your system path, you will need to
modify your loader settings to find it. On UNIX-style machines, you can
adjust the LD_LIBRARY_PATH environment variable to point to the
directory containing libclang.so.

If you are currently in the directory of this README file:


  $ PYTHONPATH=.:$PYTHONPATH LD_LIBRARY_PATH=$(llvm-config --libdir) python

Or, if you have the LLVM source tree in ~/llvm:

  $ env PYTHONPATH=$(echo ~/llvm/tools/clang/bindings/python/) \
        LD_LIBRARY_PATH=$(llvm-config --libdir) \
        python

Module Documentation
====================

For now, the easiest way to view documentation on the Python modules is
by running:

  $ pydoc clang.cindex

Testing
=======

The unit tests (located in the tests/ directory) are designed to be
executed with nosetests.

To install nosetests:

  $ pip install nosetests

Then, you can simply execute the tests by running:

  $ nosetests -v

To get an HTML code coverage report:

  $ nosetests --with-coverage --cover-html

If nosetests reports the coverage module isn't available:

  $ pip install coverage

The unit test suite should pass in full. If it doesn't, first verify the
Python bindings are loading the libclang library built from the same
source revision as the Python bindings. If it still fails, please file a
bug.
