#===- cindex.py - Python Indexing Library Bindings -----------*- python -*--===#
#
#                     The LLVM Compiler Infrastructure
#
# This file is distributed under the University of Illinois Open Source
# License. See LICENSE.TXT for details.
#
#===------------------------------------------------------------------------===#

r"""
Clang Indexing Library Bindings
===============================

This module provides an interface to the Clang indexing library. It attempts to
provide a "mid-level" interface by providing access to the low-level C APIs
while simultaneously being "Pythonic."

Some of the changes over the raw libclang API include:

 * C data types are exposed as Python classes. Methods attached to each class
   expose functionality in libclang transparently.

 * NULL is often represented as None.

 * Exceptions are raised for improper API use rather than returning semaphore
   empty/None values.

 * Strings results are converted from CXString objects to Python strings.

 * Callbacks are exposed as iterators.

A major feature of this binding over libclang is automatic memory management.
When an object is unreferenced, its libclang disposal function is called
automatically by the Python destructor. When objects are created from other
objects, a reference to the parent object is retained in the child so the
parent object will only be destroyed after all children are destroyed. If you
experience crashes due to objects being improperly disposed, please file a bug!

Class Overview
--------------

Index

  The top-level object which manages some global library state. This is
  effectively a handle into libclang. One of these must be active at all
  times.

TranslationUnit

  High-level encapsulation for parsed source files. These can be loaded from
  AST files (generated with -emit-ast from the Clang frontend). Or, in-memory
  source code can be parsed on the fly using APIs in this module.

Cursor

  Representation of an individual node in a parsed abstract syntax tree (AST).
  Cursors allow you to inspect Clang's representation of parsed source code.

CursorKind

  Represents a specific kind of Cursor. Each cursor kind (class declaration,
  variable reference, expression, etc) has a different type of this class.

Token

  Representation of a typed entity in source code. Source code is first parsed
  into tokens (literals, keywords, comments, etc).

TokenKind

  Represents a specific kind of Token.

SourceRange, SourceLocation, and File

  Objects representing information about the input source.


Known Issues and Limitations
============================

* The high-level Indexing component is not implemented. This feature has a lot
  of moving parts and will take a good amount of effort to implement.
  Contributions welcome!
  http://clang.llvm.org/doxygen/group__CINDEX__HIGH.html

* Translation Unit load failures don't expose details. libclang doesn't expose
  the reason a Translation Unit failed to load. So, we currently raise an empty
  exception if this happens. Hopefully libclang will support richer error
  reporting someday.

* Possible to segfault under some circumstances. Most (perhaps all) of the
  C APIs require an Index to be created. If you attempt to use functions like
  clang_getNullCursor() without having an Index *somewhere*, you may see a
  crash.

* No guarantees on when a destructor is called. Even though an object is a
  candidate for collection because of no remaining references, the destructor
  (__del__) may not be called for a while. This typically isn't an issue for
  short-lived processes. However, if you are using this module inside a long-
  lived process (minutes or greater) or if you are using many different
  translation units, you may wish to explicitly 'del obj' and force a garbage
  collection via the Python built-in 'gc' module to work around this.

"""

# Developer Notes
# ===============
#
# Class Types
# -----------
#
# Each class in this module can effectively be classified as one of the
# following:
#
#  * Enumeration representation (CursorKind, TokenKind, etc)
#  * libclang object representation (Cursor, Token, SourceLocation, etc)
#  * Misc (support classes)
#
# Enumeration Classes
# -------------------
#
# Enumeration classes represent enumerations defined in libclang.
#
# Instances of each enumeration class represent a specific enumerated value.
# At the minimum, each instance exposes its numeric/enumerated value and a
# string name or label. Some classes (like CursorKind) expose additional
# metadata. Each instance should be treated as a read-only static variable.
#
# Each enumeration class contains a static object which holds a mapping of
# values to class instances. This object is populated at module load time
# by calling the register() static method on the class.
#
# Each class also contains attributes that allow enumeration instances to be
# accessed by their name. e.g. CursorKind.CLASS_DECL.
#
# Ideally, we'd define each enumeration as a simple int. However, useful
# information is attached to different enumerations. e.g.
# CursorKind.is_declaration. By exposing separate class instances for each
# enumerated value, we make getting at these fields slightly easier. e.g.
# kind.is_declaration() vs CursorKind.is_declaration(kind). So, we sacrifice a
# bit of overhead and create separate class instances for each enumerated value
# at module load time.
#
# libclang Object Classes
# -----------------------
#
# These classes map Index.x typedefs to Python objects. There are 2 flavors of
# these classes. The exact flavor depends on what the underlying typedef is.
#
# If a typedef is backed by a struct, the main object class is a child of
# __builtin__.object. This class contains an inner-class which derives from
# ctypes.Structure. This inner class has the name of the C struct and defines
# the fields inside. The inner classes are fully wrapped by the outer/main
# class and should never be exposed outside of this module. These inner classes
# are also what gets passed to ctypes for the call into libclang.
#
# When returned from a C function, the structure-wrapping inner classes are
# almost always have an errcheck function registered. The errcheck function
# typically exists as a "from_struct" static method on the outer class. The
# job of this method is to take the struct and wrap it inside the outer class,
# typically be calling the constructor.
#
# For typedefs not based on structs, the main representation class is a child
# of ClangObject. ClangObject contains some common ctypes methods to proxy the
# Python object to and from a void *.
#
# Another property of object classes is that they maintain references to parent
# objects, typically a TranslationUnit. These references are necessary to
# prevent premature garbage collection of the parent object, which could cause
# the backing memory in C to get freed and Python to make a call on invalid
# memory, which would result in a segfault. If classes are derived from another
# class and require the parent to exist, the class constructor should be very
# strict and refuse to create instances if no parent is known.


# TODO
# ====
#
# o Implement clang_loadDiagnostics. This will involve supporting
#   CXDiagnosticSet. This will also require some hackery with Diagnostic since
#   no TranslationUnit is available (derived objects will want to reference a
#   TranslationUnit).
#
# o Expose CXLinkageKind, CXLanguageKind, and CXAvailabilityKind for cursors.
#
# o Expose Cursor's overwritten cursors.
#
# o Expose CXCallingConv for function types.
#
# o Implement Obj-C USR functions.

from . import enumerations

from ctypes import byref
from ctypes import c_char_p
from ctypes import c_int
from ctypes import c_longlong
from ctypes import c_uint
from ctypes import c_ulong
from ctypes import c_void_p
from ctypes import cast
from ctypes import cdll
from ctypes import CFUNCTYPE
from ctypes import POINTER
from ctypes import py_object
from ctypes import Structure
import collections

import platform
import warnings

def get_cindex_library():
    """Obtain a reference to the libclang library.

    This attempts to find libclang in the default library search directories.
    If the library cannot be found, this will raise inside the ctypes module.

    The returned instance should be fed into register_functions() to set up
    the Python prototypes.

    This function is called automatically as part of module load. You shouldn't
    need to call it outside of this module.
    """
    # FIXME: It's probably not the case that the library is actually found in
    # this location. We need a better system of identifying and loading the
    # CIndex library. It could be on path or elsewhere, or versioned, etc.
    name = platform.system()
    if name == 'Darwin':
        return cdll.LoadLibrary('libclang.dylib')
    elif name == 'Windows':
        return cdll.LoadLibrary('libclang.dll')
    else:
        return cdll.LoadLibrary('libclang.so')

# ctypes doesn't implicitly convert c_void_p to the appropriate wrapper
# object. This is a problem, because it means that from_parameter will see an
# integer and pass the wrong value on platforms where int != void*. Work around
# this by marshalling object arguments as void**.
c_object_p = POINTER(c_void_p)

# Attempt to load libclang and make it available in module scope.
lib = get_cindex_library()

# This will hold CFUNCTYPE instances for Python callbacks.
callbacks = {}

### Exception Classes ###

class TranslationUnitLoadError(Exception):
    """Represents an error that occurred when loading a TranslationUnit.

    This is raised in the case where a TranslationUnit could not be
    instantiated due to failure in the libclang library.

    FIXME: Make libclang expose additional error information in this scenario.
    """
    pass

class TranslationUnitSaveError(Exception):
    """Represents an error that occurred when saving a TranslationUnit.

    Each error has associated with it an enumerated value, accessible under
    e.save_error. Consumers can compare the value with one of the ERROR_
    constants in this class.
    """

    # Indicates that an unknown error occurred. This typically indicates that
    # I/O failed during save.
    ERROR_UNKNOWN = 1

    # Indicates that errors during translation prevented saving. The errors
    # should be available via the TranslationUnit's diagnostics.
    ERROR_TRANSLATION_ERRORS = 2

    # Indicates that the translation unit was somehow invalid.
    ERROR_INVALID_TU = 3

    def __init__(self, enumeration, message):
        assert isinstance(enumeration, int)

        if enumeration < 1 or enumeration > 3:
            raise Exception("Encountered undefined TranslationUnit save error "
                            "constant: %d. Please file a bug to have this "
                            "value supported." % enumeration)

        self.save_error = enumeration
        Exception.__init__(self, 'Error %d: %s' % (enumeration, message))

### Structures and Utility Classes ###

class CachedProperty(object):
    """Decorator that lazy-loads the value of a property.

    The first time the property is accessed, the original property function is
    executed. The value it returns is set as the new value of that instance's
    property, replacing the original method.
    """

    def __init__(self, wrapped):
        self.wrapped = wrapped
        try:
            self.__doc__ = wrapped.__doc__
        except:
            pass

    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self

        value = self.wrapped(instance)
        setattr(instance, self.wrapped.__name__, value)

        return value

class CXString(Structure):
    """Helper for transforming CXString results."""

    _fields_ = [
        ('spelling', c_char_p),
        ('free', c_int)
    ]

    def __del__(self):
        lib.clang_disposeString(self)

    @staticmethod
    def from_result(res, func, args):
        """Helper for ctypes that is called whenever a CXString is returned.

        This converts the CXString struct into a Python string.
        """
        assert isinstance(res, CXString)
        return lib.clang_getCString(res)

### Classes Defining Enumerations ###

class CXXAccessSpecifier(object):
    """Describes the C++ access level of a cursor.

    These expose whether a cursor is public, protected, or private. If a cursor
    doesn't have an access level, its access level is defined as invalid.
    """

    __slots__ = ('value', 'label')

    _value_map = {}

    def __init__(self, value, label):
        """Create a CXXAccessSpecifier type.

        To retrieve an existing specifier (which is what you probably want to
        do since access specifiers are static), call
        CXXAccessSpecifier.from_value() instead.
        """
        self.value = value
        self.label = label

    def __str__(self):
        """How this specifier is typed in a source file."""
        return self.label

    def __repr__(self):
        """System representation of type."""
        return 'CXXAccessSpecifier.%s' % self.label.upper()

    @staticmethod
    def from_value(value):
        """Obtain a CXXAccessSpecifier from its numeric value.

        This is what you should call to obtain an instance of an existing
        CXXAccessSpecifier.
        """
        result = CXXAccessSpecifier._value_map.get(value, None)
        if result is None:
            raise ValueError('Unknown CXXAccessSpecifier: %d' % value)

        return result

    @staticmethod
    def register(value, label):
        """Registers a CXXAccessSpecifier enumeration.

        This should only be called at module load time.
        """
        if value in CXXAccessSpecifier._value_map:
            raise ValueError('CXXAccessSPecifier already registered: %d' %
                    value)

        spec = CXXAccessSpecifier(value, label)
        CXXAccessSpecifier._value_map[value] = spec
        setattr(CXXAccessSpecifier, label.upper(), spec)

class CursorKind(object):
    """Descriptor for the kind of entity that a cursor points to."""

    __slots__ = (
        'name',
        'value',
    )

    _value_map = {} # int -> CursorKind

    def __init__(self, value, name):
        self.value = value
        self.name = name

    @staticmethod
    def from_value(value):
        result = CursorKind._value_map.get(value, None)

        if result is None:
            raise ValueError('Unknown CursorKind: %d' % value)

        return result

    def is_declaration(self):
        """Test if this is a declaration kind."""
        return lib.clang_isDeclaration(self)

    def is_reference(self):
        """Test if this is a reference kind."""
        return lib.clang_isReference(self)

    def is_expression(self):
        """Test if this is an expression kind."""
        return lib.clang_isExpression(self)

    def is_statement(self):
        """Test if this is a statement kind."""
        return lib.clang_isStatement(self)

    def is_attribute(self):
        """Test if this is an attribute kind."""
        return lib.clang_isAttribute(self)

    def is_invalid(self):
        """Test if this is an invalid kind."""
        return lib.clang_isInvalid(self)

    def is_translation_unit(self):
        """Test if this is a translation unit kind."""
        return lib.clang_isTranslationUnit(self)

    def is_preprocessing(self):
        """Test if this is a preprocessing kind."""
        return lib.clang_isPreprocessing(self)

    def is_unexposed(self):
        """Test if this is an unexposed kind."""
        return lib.clang_isUnexposed(self)

    def from_param(self):
        """ctyped helper to convert instance to function argument."""
        return self.value

    def __repr__(self):
        return 'CursorKind.%s' % (self.name,)

    @staticmethod
    def get_all_kinds():
        """Return all CursorKind enumeration instances."""
        return CursorKind._value_map.values()

    @staticmethod
    def register(value, name):
        """Registers a new kind type.

        This is typically called only at module load time. External users
        should not need to ever call this.
        """
        if value in CursorKind._value_map:
            raise ValueError('CursorKind already registered: %d' % value)

        kind = CursorKind(value, name)
        CursorKind._value_map[value] = kind
        setattr(CursorKind, name, kind)

class ResourceUsageKind(object):
    """Represents a kind of resource usage."""

    _value_map = {}

    __slots__ = (
        'name',
        'value',
    )

    def __init__(self, value, name):
        """Create a new resource usage kind instance.

        Since ResourceUsageKinds are static, this should only be done at
        module load time. i.e. you should not create new instances outside of
        this module.
        """
        self.value = value
        self.name = name

    @staticmethod
    def from_value(value):
        """Obtain a ResourceUsageKind from its numeric value."""
        result = ResourceUsageKind._value_map.get(value, None)

        if result is None:
            raise ValueError('Unknown ResourceUsageKind: %d' % value)

        return result

    @staticmethod
    def register(value, name):
        kind = ResourceUsageKind(value, name)
        ResourceUsageKind._value_map[value] = kind
        setattr(ResourceUsageKind, name, kind)

    def __repr__(self):
        return 'ResourceUsageKind.%s' % self.name

class TokenKind(object):
    """Describes a specific type of a Token."""

    _value_map = {} # int -> TokenKind

    def __init__(self, value, name):
        """Create a new TokenKind instance from a numeric value and a name."""
        self.value = value
        self.name = name

    def __repr__(self):
        return 'TokenKind.%s' % (self.name,)

    @staticmethod
    def from_value(value):
        """Obtain a registered TokenKind instance from its value."""
        result = TokenKind._value_map.get(value, None)

        if result is None:
            raise ValueError('Unknown TokenKind: %d' % value)

        return result

    @staticmethod
    def register(value, name):
        """Register a new TokenKind enumeration.

        This should only be called at module load time by code within this
        package.
        """
        if value in TokenKind._value_map:
            raise ValueError('TokenKind already registered: %d' % value)

        kind = TokenKind(value, name)
        TokenKind._value_map[value] = kind
        setattr(TokenKind, name, kind)

class TypeKind(object):
    """Describes the kind of type."""

    __slots__ = (
        'name',
        'value'
    )

    _value_map = {}

    def __init__(self, value, name):
        self.name = name
        self.value = value

    @property
    def spelling(self):
        """Retrieve the spelling of this TypeKind."""
        return lib.clang_getTypeKindSpelling(self.value)

    def from_param(self):
        return self.value

    def __repr__(self):
        return 'TypeKind.%s' % (self.name,)

    @staticmethod
    def from_value(value):
        result = TypeKind._value_map.get(value, None)

        if result is None:
            raise ValueError('Unknown TypeKind: %d' % value)

        return result

    @staticmethod
    def register(value, name):
        """Registers a new TypeKind.

        This should not be called outside of the module.
        """
        if value in TypeKind._value_map:
            raise ValueError('TypeKind value already registered: %d' % value)

        kind = TypeKind(value, name)
        TypeKind._value_map[value] = kind
        setattr(TypeKind, name, kind)

### Source Location Classes ###

class SourceLocation(object):
    """Represents a particular location within a source file.

    A SourceLocation refers to the position of an entity within a file. This
    position can be addressed by its file character offset or by a line-column
    pair.

    Each location comes in 3 different flavors: expansion, presumed, and
    spelling. These are exposed through the expansion_location,
    presumed_location, and spelling_location properties, respectively.

    The file, line, column, and offset properties access the expansion
    location and are provided as a convenience.
    """

    class CXSourceLocation(Structure):
        """Representation of CXSourceLocation structure.

        This is an internal class and it should only be used from within this
        module.
        """
        _fields_ = [
            ('ptr_data', c_void_p * 2),
            ('int_data', c_uint)
        ]

    def __init__(self,
                 structure=None,
                 tu=None,
                 source=None,
                 line=None,
                 column=None,
                 offset=None):
        """Create a new SourceLocation instance.

        SourceLocations can be instantiated one of a few ways:

          * Through data structures returned by libclang. Pass the structure
            and tu arguments.
          * From a line/column location in a file. Pass the line and column
            arguments as well as the source file. If the source file is defined
            as a string filename, you must also pass tu with the TranslationUnit
            to which this file belongs. If the source file is a File, you do not
            need to pass a TranslationUnit, as it is obtained from the passed File.
          * From a character offset in a file. This is similar to the above
            except instead of passing line and column, pass offset.

        If multiple construction methods are passed, behavior is undefined.

        When requesting a location by file location, the returned location may
        represent a different location from the one requested. The rules are as
        follows:

          * If a location past the end of file is requested, the returned
            location represents the actual end of the file.

          * If the location is in the middle of a AST cursor, the location
            location corresponding with the first character in that cursor's
            source range is returned.

        Arugments:

        structure -- SourceLocation.CXSourceLocation from which to instantiate
          an instance.
        tu -- TranslationUnit to which this location belongs. This is optional
          when source is a File instance.
        source -- Provided when construction a location manually. Must be the
          str filename of the source file or a File instance corresponding to
          the file.
        line -- int line number of location to construct. The first line in a
          file is 1.
        column -- int column number of location to construct. Must be provided
          with line. The first column in a line is 1.
        offset -- int character offset in file to construct from. The first
          character in a file is 0.
        """

        if structure is not None:
            assert isinstance(structure, SourceLocation.CXSourceLocation)

        if tu is not None:
            assert isinstance(tu, TranslationUnit)

        if source is not None:
            assert isinstance(source, (File, str))

        if line is not None:
            assert line > 0

        if column is not None:
            assert column > 0

        if offset is not None:
            assert offset >= 0

        if structure is not None:
            assert tu is not None
            self._struct = structure
            self._tu = tu
            return

        if source is None:
            raise ValueError('source or structure argument must be defined.')

        input_file = None

        if isinstance(source, str):
            if tu is None:
                raise ValueError('tu must be defined when source is a str.')

            input_file = File.from_name(tu, source)
        else:
            input_file = source
            tu = source.translation_unit

        self._tu = tu

        if line is not None and column is not None:
            self._struct = lib.clang_getLocation(tu, input_file, line, column)
            return

        if offset is not None:
            self._struct = lib.clang_getLocationForOffset(tu, input_file,
                    offset)
            return

        raise Exception('No construction sources defined.')

    @CachedProperty
    def expansion_location(self):
        """Get a 4-tuple of the expansion location of this location.

        The returned tuple has fields (file, line, column, offset). file
        is a File instance and the rest of the arguments are ints.
        """
        f = c_object_p()
        line, column, offset = c_uint(), c_uint(), c_uint()

        lib.clang_getExpansionLocation(self._struct, byref(f), byref(line),
                                       byref(column), byref(offset))

        if not f:
            raise Exception('Could not resolve SourceLocation.')

        return (File(f), int(line.value), int(column.value), int(offset.value))

    @CachedProperty
    def presumed_location(self):
        """Get a 3-tuple representing the presumed location of this location.

        The returned tuple has fields (file, line, column). file is a File
        instance and the others are ints.
        """
        f = c_object_p()
        line, column = c_uint(), c_uint()

        lib.clang_getPresumedLocation(self._struct, byref(f), byref(line),
                                      byref(column))

        if not f:
            raise Exception('Could not resolve SourceLocation.')

        return (File(f), int(line.value), int(column.value))

    @CachedProperty
    def spelling_location(self):
        """Get a 4-tuple representing the location of the spelling for this
        location.

        The returned tuple has fields (file, line, column, offset). file is a
        File instance and the others are ints.
        """
        f = c_object_p()
        line, column, offset = c_uint(), c_uint(), c_uint()

        lib.clang_getSpellingLocation(self._struct, byref(f), byref(line),
                                      byref(column), byref(offset))

        if not f:
            raise Exception('Could not resolve SourceLocation.')

        return (File(f), int(line.value), int(column.value), int(offset.value))

    @property
    def file(self):
        """Get the file represented by this source location.

        Returns a File instance.
        """
        return self.expansion_location[0]

    @property
    def line(self):
        """Get the line number represented by this source location."""
        return self.expansion_location[1]

    @property
    def column(self):
        """Get the column represented by this source location."""
        return self.expansion_location[2]

    @property
    def offset(self):
        """Get the file offset represented by this source location."""
        return self.expansion_location[3]

    @property
    def translation_unit(self):
        """Get the TranslationUnit to which this location belongs."""
        return self._tu

    def __eq__(self, other):
        return lib.clang_equalLocations(self._struct, other._struct)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        if self.file:
            filename = self.file.name
        else:
            filename = None
        return "<SourceLocation file %r, line %r, column %r>" % (
            filename, self.line, self.column)

    def from_param(self):
        """ctypes helper to convert instance to library parameter."""
        return self._struct

    @staticmethod
    def from_struct(res, func, arguments):
        """ctypes helper to convert a CXSourceLocation into a SourceLocation."""
        assert isinstance(res, SourceLocation.CXSourceLocation)

        tu = None

        for arg in arguments:
            if isinstance(arg, TranslationUnit):
                tu = arg
                break

            if hasattr(arg, 'translation_unit'):
                tu = arg.translation_unit
                break

        if tu is None:
            raise Exception('TranslationUnit not found when creating '
                             'SourceLocation.')

        return SourceLocation(structure=res, tu=tu)

    @staticmethod
    def from_position(tu, file, line, column):
        """DEPRECATED Obtain a SourceLocation associated with a given
        file/line/column in a translation unit.

        Use __init__(file, line, column) or __init__(tu, filename, line,
        column) instead.
        """
        warnings.warn('Switch to SourceLocation() constructor.',
                DeprecationWarning)
        return SourceLocation(tu=tu, source=file, line=line, column=column)

    @staticmethod
    def from_offset(tu, file, offset):
        """DEPRECATED Retrieve a SourceLocation from a given character offset.

        tu -- TranslationUnit file belongs to
        file -- File instance to obtain offset from
        offset -- Integer character offset within file
        """
        warnings.warn('Switch to SourceLocation() constructor.',
                DeprecationWarning)
        return SourceLocation(tu=tu, source=file, offset=offset)

class SourceRange(object):
    """Describe a range over two source locations within source code.

    This is effectively a container for 2 SourceLocation instances.
    """
    class CXSourceRange(Structure):
        """Wrapper for CXSourceRange structure.

        This is an internal class and should not be used outside the module.
        """
        _fields_ = [
            ('ptr_data', c_void_p * 2),
            ('begin_int_data', c_uint),
            ('end_int_data', c_uint)
        ]

    def __init__(self, start=None, end=None, structure=None, tu=None):
        """Construct a SourceRange instance.

        Instances can be constructed by passing a stand and end SourceLocation
        or by passing a CXSourceRange structure.

        If passing a CXSourceRange structure, tu must also be defined.
        Otherwise, it is obtained from the start argument.

        It is an error to pass SourceLocations referring to separate
        TranslationUnits.

        If both the start/end arguments and structure are defined, behavior is
        undefined.

        Arguments:

        start -- SourceLocation representing the start of the range.
        end -- SourceLocation representing the end of the range.
        structure -- SourceRange.CXSourceRange instance.
        tu -- TranslationUnit this range belongs to.
        """
        if start is not None:
            assert isinstance(start, SourceLocation)

        if end is not None:
            assert isinstance(end, SourceLocation)

        if structure is not None:
            assert isinstance(structure, SourceRange.CXSourceRange)

        if tu is not None:
            assert isinstance(tu, TranslationUnit)

        self._struct = structure

        if structure is not None:
            if tu is None:
                raise ValueError('tu must be defined when constructing from ' +
                                 'struct.')
            self._struct.translation_unit = tu
            return

        assert isinstance(start.translation_unit, TranslationUnit)
        assert start.translation_unit == end.translation_unit
        self._struct = lib.clang_getRange(start.from_param(), end.from_param())
        self._struct.translation_unit = start.translation_unit

    @CachedProperty
    def start(self):
        """Return a SourceLocation representing the first character within this
        range.
        """
        return lib.clang_getRangeStart(self._struct)

    @CachedProperty
    def end(self):
        """Return a SourceLocation representing the last character within this
        range.
        """
        return lib.clang_getRangeEnd(self._struct)

    def __eq__(self, other):
        return lib.clang_equalRanges(self._struct, other._struct)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return "<SourceRange start %r, end %r>" % (self.start, self.end)

    def from_param(self):
        """ctypes helper to convert instance to libclang parameter."""
        return self._struct

    @staticmethod
    def from_struct(res, func, arguments):
        """ctypes helper to convert a CXSourceRange into a SourceRange."""
        assert isinstance(res, SourceRange.CXSourceRange)

        tu = None
        for arg in arguments:
            if isinstance(arg, TranslationUnit):
                tu = arg
                break

            if hasattr(arg, 'translation_unit'):
                tu = arg.translation_unit
                break

        if tu is None:
            raise Exception('TranslationUnit not found when creating '
                            'SourceRange.')

        return SourceRange(structure=res, tu=tu)

    @staticmethod
    def from_locations(start, end):
        """DEPRECATED Create a SourceRange from 2 SourceLocations.

        The SourceRange() constructor should be used instead.
        """
        warnings.warn('Switch to SourceRange() constructor.',
                DeprecationWarning)
        return SourceRange(start=start, end=end)

class Diagnostic(object):
    """
    A Diagnostic is a single instance of a Clang diagnostic. It includes the
    diagnostic severity, the message, the location the diagnostic occurred, as
    well as additional source ranges and associated fix-it hints.

    A Diagnostic is instantiated by retrieving it from a TranslationUnit's
    diagnostics iterator.
    """

    Ignored = 0
    Note    = 1
    Warning = 2
    Error   = 3
    Fatal   = 4

    __slots__ = (
        '_ptr',
        '_tu',
    )

    def __init__(self, ptr, tu=None):
        assert isinstance(tu, TranslationUnit)

        self._ptr = ptr
        self._tu = tu

    def __del__(self):
        lib.clang_disposeDiagnostic(self)

    @property
    def severity(self):
        return lib.clang_getDiagnosticSeverity(self)

    @property
    def location(self):
        return lib.clang_getDiagnosticLocation(self)

    @property
    def spelling(self):
        return lib.clang_getDiagnosticSpelling(self)

    @property
    def ranges(self):
        class RangeIterator:
            def __init__(self, diag):
                self.diag = diag

            def __len__(self):
                return int(lib.clang_getDiagnosticNumRanges(self.diag))

            def __getitem__(self, key):
                if (key >= len(self)):
                    raise IndexError
                return lib.clang_getDiagnosticRange(self.diag, key)

        return RangeIterator(self)

    @property
    def fixits(self):
        class FixItIterator:
            def __init__(self, diag):
                self.diag = diag

            def __len__(self):
                return int(lib.clang_getDiagnosticNumFixIts(self.diag))

            def __getitem__(self, key):
                fix_range = SourceRange.CXSourceRange()
                value = lib.clang_getDiagnosticFixIt(self.diag, key,
                        byref(fix_range))
                if len(value) == 0:
                    raise IndexError

                new_range = SourceRange(structure=fix_range, tu=self.diag._tu)
                return FixIt(new_range, value)

        return FixItIterator(self)

    @property
    def category_number(self):
        """The category number for this diagnostic."""
        return lib.clang_getDiagnosticCategory(self)

    @property
    def category_name(self):
        """The string name of the category for this diagnostic."""
        return lib.clang_getDiagnosticCategoryName(self.category_number)

    @property
    def option(self):
        """The command-line option that enables this diagnostic."""
        return lib.clang_getDiagnosticOption(self, None)

    @property
    def disable_option(self):
        """The command-line option that disables this diagnostic."""
        disable = CXString()
        lib.clang_getDiagnosticOption(self, byref(disable))

        return lib.clang_getCString(disable)

    @property
    def translation_unit(self):
        """The TranslationUnit from which the Diagnostic was derived."""
        return self._tu

    def __repr__(self):
        return "<Diagnostic severity %r, location %r, spelling %r>" % (
            self.severity, self.location, self.spelling)

    def from_param(self):
        """ctypes helper to convert instance to argument."""
        return self._ptr

class FixIt(object):
    """
    A FixIt represents a transformation to be applied to the source to
    "fix-it". The fix-it shouldbe applied by replacing the given source range
    with the given value.
    """

    def __init__(self, range, value):
        self.range = range
        self.value = value

    def __repr__(self):
        return "<FixIt range %r, value %r>" % (self.range, self.value)


class Cursor(object):
    """An element with the abstract syntax tree of a translation unit.

    The cursor abstraction unifies many different entities, including
    declarations, statements, expressions, and references.

    Cursors are never instantiated directly. Instead, they are created from
    another pre-existing object, like a TranslationUnit.
    """

    class CXCursor(Structure):
        """Low-level representation of a cursor."""
        _fields_ = [
            ('kind', c_uint),
            ('xdata', c_int),
            ('data', c_void_p * 3)
        ]

    def __init__(self, location=None, structure=None, tu=None):
        """Instantiate a cursor instance.

        Currently, we only support creating cursors from CXCursor instances.
        Cursors should have a TranslationUnit associated with them. The
        reference to the TU prevents the GC from collecting the TU before the
        Cursor.
        """

        if location is not None:
            assert isinstance(location, SourceLocation)

        if structure is not None:
            assert isinstance(structure, Cursor.CXCursor)

        if tu is not None:
            assert isinstance(tu, TranslationUnit)

        if location is not None:
            tu = location.translation_unit
            self._struct = lib.clang_getCursor(tu, location.from_param())
            self._struct.translation_unit = tu
            return

        self._struct = structure
        self._struct.translation_unit = tu

    def __eq__(self, other):
        return lib.clang_equalCursors(self._struct, other._struct)

    def __ne__(self, other):
        return not self.__eq__(other)

    def is_null(self):
        """Returns True if this cursor is the special null cursor.

        Various libclang APIs return the null cursor if there was an error or
        if the requested cursor did not exists.
        """
        return lib.clang_Cursor_isNull(self._struct)

    def is_definition(self):
        """
        Returns true if the declaration pointed at by the cursor is also a
        definition of that entity.
        """
        return lib.clang_isCursorDefinition(self._struct)

    def is_static_method(self):
        """Returns True if the cursor refers to a C++ member function or member
        function template that is declared 'static'.
        """
        return lib.clang_CXXMethod_isStatic(self)

    def is_virtual_base(self):
        """Determine if the base class specified by this Cursor is virtual.

        If this cursor does not point to a valid kind, an exception is raised.
        """
        return lib.clang_CXXMethod_isStatic(self._struct)

    def is_virtual_method(self):
        """Determine whether the C++ member function is virtual or overwrites a
        virtual method.

        Returns True if it does. Returns False if it is a non-virtual method or
        if the cursor does not refer to a member function or member function
        template.
        """
        return lib.clang_CXXMethod_isVirtual(self._struct)

    def get_definition(self):
        """
        If the cursor is a reference to a declaration or a declaration of
        some entity, return a cursor that points to the definition of that
        entity.
        """
        # TODO: Should probably check that this is either a reference or
        # declaration prior to issuing the lookup.
        return lib.clang_getCursorDefinition(self._struct)

    def get_usr(self):
        """Return the Unified Symbol Resultion (USR) for the entity referenced
        by the given cursor (or None).

        A Unified Symbol Resolution (USR) is a string that identifies a
        particular entity (function, class, variable, etc.) within a
        program. USRs can be compared across translation units to determine,
        e.g., when references in one translation refer to an entity defined in
        another translation unit."""
        return lib.clang_getCursorUSR(self._struct)

    @property
    def kind(self):
        """Return the kind of this cursor."""
        return CursorKind.from_value(self._struct.kind)

    @property
    def template_kind(self):
        """Return the CursorKind of the specializations that would be generated
        by instantiating the template.

        This can be used to determine whether a template is declared with
        "struct," "class," "or "union," for example.

        If the cursor does not refer to a template, None is returned.
        """
        result = lib.clang_getTemplateCursorKind(self._struct)
        if result == CursorKind.NO_DECL_FOUND:
            return None

        return result

    @property
    def template_specialization(self):
        """Retrieve the Cursor to the template this Cursor specializes or from
        which it was instantiated.

        Returns None if this Cursor is not a specialization of a template.
        """
        return lib.clang_getSpecializedCursorTemplate(self._struct)

    @CachedProperty
    def spelling(self):
        """Return the spelling of the entity pointed at by the cursor."""
        if not self.kind.is_declaration():
            # FIXME: clang_getCursorSpelling should be fixed to not assert on
            # this, for consistency with clang_getCursorUSR.
            return None

        return lib.clang_getCursorSpelling(self._struct)

    @CachedProperty
    def displayname(self):
        """
        Return the display name for the entity referenced by this cursor.

        The display name contains extra information that helps identify the cursor,
        such as the parameters of a function or template or the arguments of a
        class template specialization.
        """
        return lib.clang_getCursorDisplayName(self._struct)

    @CachedProperty
    def location(self):
        """
        Return the source location (the starting character) of the entity
        pointed at by the cursor.
        """
        return lib.clang_getCursorLocation(self._struct)

    @CachedProperty
    def extent(self):
        """
        Return the source range (the range of text) occupied by the entity
        pointed at by the cursor.
        """
        return lib.clang_getCursorExtent(self._struct)

    @CachedProperty
    def type(self):
        """
        Retrieve the Type (if any) of the entity pointed at by the cursor.
        """
        return lib.clang_getCursorType(self._struct)

    @CachedProperty
    def referenced(self):
        """Return the Cursor referenced by this Cursor.

        If no Cursor is referenced by this Cursor, returns None.
        """
        return lib.clang_getCursorReferenced(self._struct)

    @CachedProperty
    def canonical(self):
        """Return the canonical Cursor corresponding to this Cursor.

        The canonical cursor is the cursor which is representative for the
        underlying entity. For example, if you have multiple forward
        declarations for the same class, the canonical cursor for the forward
        declarations will be identical.
        """
        return lib.clang_getCanonicalCursor(self._struct)

    @CachedProperty
    def result_type(self):
        """Retrieve the Type of the result for this Cursor."""
        return lib.clang_getResultType(self.type._struct)

    @CachedProperty
    def underlying_typedef_type(self):
        """Return the underlying type of a typedef declaration.

        Returns a Type for the typedef this cursor is a declaration for. If
        the current cursor is not a typedef, this raises.
        """
        assert self.kind.is_declaration()
        return lib.clang_getTypedefDeclUnderlyingType(self._struct)

    @CachedProperty
    def enum_type(self):
        """Return the integer type of an enum declaration.

        Returns a Type corresponding to an integer. If the cursor is not for an
        enum, this raises.
        """
        assert self.kind == CursorKind.ENUM_DECL
        return lib.clang_getEnumDeclIntegerType(self._struct)

    @property
    def enum_value(self):
        """Return the value of an enum constant."""
        if not hasattr(self, '_enum_value'):
            assert self.kind == CursorKind.ENUM_CONSTANT_DECL
            # Figure out the underlying type of the enum to know if it
            # is a signed or unsigned quantity.
            underlying_type = self.type
            if underlying_type.kind == TypeKind.ENUM:
                underlying_type = underlying_type.get_declaration().enum_type
            if underlying_type.kind in (TypeKind.CHAR_U,
                                        TypeKind.UCHAR,
                                        TypeKind.CHAR16,
                                        TypeKind.CHAR32,
                                        TypeKind.USHORT,
                                        TypeKind.UINT,
                                        TypeKind.ULONG,
                                        TypeKind.ULONGLONG,
                                        TypeKind.UINT128):
                self._enum_value = Cursor_enum_const_decl_unsigned(self)
            else:
                self._enum_value = Cursor_enum_const_decl(self)
        return self._enum_value

    @CachedProperty
    def objc_type_encoding(self):
        """Return the Objective-C type encoding as a str."""
        return lib.clang_getDeclObjCTypeEncoding(self._struct)

    @CachedProperty
    def access_specifier(self):
        """Returns the access control level for a base or access specifier
        cursor.
        """
        return CXXAccessSpecifier.from_value(
                lib.clang_getCXXAccessSpecifier(self._struct))

    @CachedProperty
    def overloaded_declaration_count(self):
        """Return the number of overloaded declarations referenced by this
        Cursor.

        If this Cursor is not a CursorKind.OVERLOADED_DECL_REF, this will
        raise.
        """
        assert self.kind == CursorKind.OVERLOADED_DECL_REF
        return lib.clang_getNumOverloadedDecls(self._struct)

    def get_overloaded_declaration(self, index):
        """Retrieve a Cursor for a specific overloaded declaration referenced
        by this Cursor.

        If this Cursor does not reference overloaded declarations or if the
        index is not valid, this will raise.
        """
        assert isinstance(index, int)
        assert self.kind == CursorKind.OVERLOADED_DECL_REF
        return lib.clang_getOverloadedDecl(self._struct, index)

    @property
    def overloaded_declarations(self):
        """Generator for Cursor instances representing the overloaded
        declarations referenced by this Cursor.

        If this Cursor is not a CursorKind.OVERLOADED_DECL_REF, this will
        raise.
        """
        for i in range(0, self.overloaded_declaration_count):
            yield self.get_overloaded_declaration(i)

    @CachedProperty
    def hash(self):
        """Returns a hash of the cursor as an int."""
        return lib.clang_hashCursor(self._struct)

    @property
    def semantic_parent(self):
        """Return the semantic parent for this cursor."""
        if not hasattr(self, '_semantic_parent'):
            self._semantic_parent = Cursor_semantic_parent(self)

        return self._semantic_parent

    @property
    def lexical_parent(self):
        """Return the lexical parent for this cursor."""
        if not hasattr(self, '_lexical_parent'):
            self._lexical_parent = Cursor_lexical_parent(self)

        return self._lexical_parent

    @property
    def translation_unit(self):
        """Returns the TranslationUnit to which this Cursor belongs."""
        return self._struct.translation_unit

    @property
    def ib_outlet_collection_type(self):
        """Returns the collection element Type for an IB Outlet Collection
        attribute."""
        return lib.clang_getIBOutletCollectionType(self._struct)

    @property
    def included_file(self):
        """Returns the File that is included by the current inclusion cursor."""
        assert self.kind == CursorKind.INCLUSION_DIRECTIVE

        return lib.clang_getIncludedFile(self._struct)

    @property
    def translation_unit(self):
        """Returns the TranslationUnit to which this Cursor belongs."""
        return self._struct.translation_unit

    def get_children(self):
        """Return an iterator for accessing the children of this cursor."""

        # TODO Support recursion.
        # TODO Implement as true iterator without buffering.
        # FIXME: Expose iteration from CIndex, PR6125.
        def visitor(child, parent, children):
            cursor = Cursor(structure=child, tu=self._struct.translation_unit)

            # FIXME: Document this assertion in API.
            assert not cursor.is_null()

            children.append(cursor)

            return 1 # continue
        children = []
        lib.clang_visitChildren(self._struct,
                                callbacks['cursor_visit'](visitor),
                                children)
        return iter(children)

    def get_tokens(self):
        """Obtain the Tokens that constitute this token.

        This is a merely a convenience method that calls into
        TranslationUnit.get_tokens().

        This method is a generator of Token instances.
        """
        for t in self.translation_unit.get_tokens(sourcerange=self.extent):
            yield t

    def get_reference_name_extent(self,
                                  index=0,
                                  qualifier=False,
                                  template_arguments=False,
                                  single_piece=False):
        """Obtain the SourceRange for the thing referenced by this Cursor.

        This is only valid on cursors that reference something else. If the
        cursor does not reference something, None will be returned.

        Some referenced cursors refer to multiple source ranges. You have 2
        options: 1) force these to be combined together by setting single_piece
        to True 2) Query each separately through the index argument.

        Unfortunately, libclang does not expose an API to say how many source
        ranges are available for a referenced cursor. So, the only way to
        obtain the multiple individual SourceRange instances is to call this
        method with an incrementing index argument until None is returned. The
        get_reference_name_extents() method is a convenience wrapper that does
        this.

        Arguments:

        index -- The numeric 0-indexed piece to retrieve. If single_piece is
        True, only 0 is valid.
        qualifier -- Include the nested-name specifier in the return value.
        template_arguments -- Include explicit template arguments in the return
        value.
        single_piece -- If True and the name is non-contiguous, return the full
        spanning range.
        """
        flags = 0
        if qualifier:
            flags |= 1
        if template_arguments:
            flags |= 2
        if single_piece:
            flags |= 4
            index = 0

        return lib.clang_getCursorReferenceNameRange(self._struct, flags, index)

    def get_reference_name_extents(self):
        raise Exception('Not yet implemented.')

    @staticmethod
    def from_struct(res, func, arguments):
        """ctypes errcheck handler to convert CXCursor into a Cursor."""
        assert isinstance(res, Cursor.CXCursor)

        # FIXME: There should just be an isNull method.
        #if res == lib.clang_getNullCursor():
        #    return None

        # Store a reference to the TU in the Python object so it won't get GC'd
        # before the Cursor.
        tu = None
        for arg in arguments:
            if isinstance(arg, TranslationUnit):
                tu = arg
                break

            if hasattr(arg, 'translation_unit'):
                tu = arg.translation_unit
                break

        assert tu is not None

        return Cursor(structure=res, tu=tu)

    @staticmethod
    def from_location(tu, location):
        """DEPRECATED Construct a Cursor from a SourceLocation.

        Use the Cursor() constructor instead.
        """
        warnings.warn('Switch to Cursor() constructor.', DeprecationWarning)
        return Cursor(location=location, tu=tu)

class Type(object):
    """The type of an element in the abstract syntax tree."""
    class CXType(Structure):
        """Wrapper for CXType structs.

        This is an internal class and should not be used outside of the module.
        """

        _fields_ = [
            ('kind_id', c_int),
            ('data', c_void_p * 2)
        ]

    __slots__ = (
        '_struct',
    )

    def __init__(self, structure=None, tu=None):
        assert isinstance(structure, Type.CXType)
        assert isinstance(tu, TranslationUnit)

        self._struct = structure
        self._struct.translation_unit = tu

    @property
    def kind(self):
        """Return the kind of this type."""
        return TypeKind.from_value(self._struct.kind_id)

    def argument_types(self):
        """Retrieve a container for the non-variadic arguments for this type.

        The returned object is iterable and indexable. Each item in the
        container is a Type instance.
        """
        class ArgumentsIterator(collections.Sequence):
            def __init__(self, parent):
                self.parent = parent
                self.length = None

            def __len__(self):
                if self.length is None:
                    self.length = lib.clang_getNumArgTypes(self.parent)

                return self.length

            def __getitem__(self, key):
                # FIXME Support slice objects.
                if not isinstance(key, int):
                    raise TypeError("Must supply a non-negative int.")

                if key < 0:
                    raise IndexError("Only non-negative indexes are accepted.")

                if key >= len(self):
                    raise IndexError("Index greater than container length: "
                                     "%d > %d" % ( key, len(self) ))

                result = lib.clang_getArgType(self.parent, key)
                if result.kind == TypeKind.INVALID:
                    raise IndexError("Argument could not be retrieved.")

                return result

        assert self.kind == TypeKind.FUNCTIONPROTO
        return ArgumentsIterator(self._struct)

    @property
    def element_type(self):
        """Retrieve the Type of elements within this Type.

        If accessed on a type that is not an array, complex, or vector type, an
        exception will be raised.
        """
        result = lib.clang_getElementType(self._struct)
        if result.kind == TypeKind.INVALID:
            raise Exception('Element type not available on this type.')

        return result

    @property
    def element_count(self):
        """Retrieve the number of elements in this type.

        Returns an int.

        If the Type is not an array or vector, this raises.
        """
        result = lib.clang_getNumElements(self._struct)
        if result < 0:
            raise Exception('Type does not have elements.')

        return result

    def get_canonical(self):
        """Return the canonical type for a Type.

        Clang's type system explicitly models typedefs and all the ways a
        specific type can be represented.  The canonical type is the underlying
        type with all the "sugar" removed.  For example, if 'T' is a typedef
        for 'int', the canonical type for 'T' would be 'int'.
        """
        return lib.clang_getCanonicalType(self._struct)

    def is_const_qualified(self):
        """Determine whether a Type has the "const" qualifier set.

        This does not look through typedefs that may have added "const"
        at a different level.
        """
        return lib.clang_isConstQualifiedType(self._struct)

    def is_volatile_qualified(self):
        """Determine whether a Type has the "volatile" qualifier set.

        This does not look through typedefs that may have added "volatile"
        at a different level.
        """
        return lib.clang_isVolatileQualifiedType(self._struct)

    def is_restrict_qualified(self):
        """Determine whether a Type has the "restrict" qualifier set.

        This does not look through typedefs that may have added "restrict" at
        a different level.
        """
        return lib.clang_isRestrictQualifiedType(self._struct)

    def is_function_variadic(self):
        """Determine whether this function Type is a variadic function type."""
        assert self.kind == TypeKind.FUNCTIONPROTO

        return lib.clang_isFunctionTypeVariadic(self._struct)

    def is_pod(self):
        """Determine whether this Type represents plain old data (POD)."""
        return lib.clang_isPODType(self._struct)

    def get_pointee(self):
        """
        For pointer types, returns the type of the pointee.
        """
        return lib.clang_getPointeeType(self._struct)

    def get_declaration(self):
        """
        Return the cursor for the declaration of the given type.
        """
        return lib.clang_getTypeDeclaration(self._struct)

    def get_result(self):
        """
        Retrieve the result type associated with a function type.
        """
        return lib.clang_getResultType(self._struct)

    def get_array_element_type(self):
        """
        Retrieve the type of the elements of the array type.
        """
        return lib.clang_getArrayElementType(self._struct)

    def get_array_size(self):
        """
        Retrieve the size of the constant array.
        """
        return lib.clang_getArraySize(self._struct)

    @property
    def translation_unit(self):
        """Get the TranslationUnit from which this instance was derived."""
        return self._struct.translation_unit

    def __eq__(self, other):
        if type(other) != type(self):
            return False

        return lib.clang_equalTypes(self._struct, other._struct)

    def __ne__(self, other):
        return not self.__eq__(other)

    @staticmethod
    def from_struct(res, func, args):
        assert isinstance(res, Type.CXType)

        tu = None
        for arg in args:
            if isinstance(arg, TranslationUnit):
                tu = arg
                break

            if hasattr(arg, 'translation_unit'):
                tu = arg.translation_unit
                break

        if tu is None:
            raise Exception('TranslationUnit not found when creating Type.')

        return Type(structure=res, tu=tu)

class TokenKind(object):
    """Describes a specific type of a Token."""

    _value_map = {} # int -> TokenKind

    def __init__(self, value, name):
        """Create a new TokenKind instance from a numeric value and a name."""
        self.value = value
        self.name = name

    def __repr__(self):
        return 'TokenKind.%s' % (self.name,)

    @staticmethod
    def from_value(value):
        """Obtain a registered TokenKind instance from its value."""
        result = TokenKind._value_map.get(value, None)

        if result is None:
            raise ValueError('Unknown TokenKind: %d' % value)

        return result

    @staticmethod
    def register(value, name):
        """Register a new TokenKind enumeration.

        This should only be called at module load time by code within this
        package.
        """
        if value in TokenKind._value_map:
            raise ValueError('TokenKind already registered: %d' % value)

        kind = TokenKind(value, name)
        TokenKind._value_map[value] = kind
        setattr(TokenKind, name, kind)

class Token(object):
    """Represents a token from a source file.

    A token is an entity extracted by the parser. These include things like
    keywords, identifiers, comments, etc.

    Token instances can be obtained by calling TranslationUnit.get_tokens().
    The API does not currently support direct creation of tokens.
    """

    class CXToken(Structure):
        """Represents a CXToken structure.

        This is an internal class and shouldn't be used outside of the module.
        """

        _fields_ = [
            ('int_data', c_uint * 4),
            ('ptr_data', c_void_p)
        ]

    def __init__(self, structure=None, tu=None):
        assert isinstance(structure, Token.CXToken)

        if tu is not None:
            assert isinstance(tu, TranslationUnit)

        self._struct = structure
        self._struct.translation_unit = tu

    @CachedProperty
    def kind(self):
        """The TokenKind for this token."""
        return TokenKind.from_value(lib.clang_getTokenKind(self._struct))

    @CachedProperty
    def spelling(self):
        """The spelling for this token.

        This is the literal text defining the token.
        """
        return lib.clang_getTokenSpelling(self._struct.translation_unit,
                                          self._struct)

    @CachedProperty
    def location(self):
        """The location of this token.

        Returns a SourceLocation instance.
        """
        return lib.clang_getTokenLocation(self._struct.translation_unit,
                                          self._struct)

    @CachedProperty
    def extent(self):
        """The source locations this token occupies.

        Returns a SourceRange instance.
        """
        return lib.clang_getTokenExtent(self._struct.translation_unit,
                                        self._struct)


    @CachedProperty
    def cursor(self):
        """Retrieve the Cursor this Token corresponds to."""
        cursor = Cursor.CXCursor()
        lib.clang_annotateTokens(self._struct.translation_unit,
                                 byref(self._struct), 1, byref(cursor))

        return Cursor(structure=cursor, tu=self._struct.translation_unit)

## CIndex Objects ##

class ClangObject(object):
    """Base class for Clang objects.

    This is the common base class for all Clang types that are represented as
    void * types. The purpose of this class is to marshall types between Python
    and libclang through the ctypes module.

    This class should never be instantiated directly, only through children.
    """
    def __init__(self, obj):
        assert isinstance(obj, c_object_p) and obj
        self.obj = self._as_parameter_ = obj

    def from_param(self):
        return self._as_parameter_


class _CXUnsavedFile(Structure):
    """Helper for passing unsaved file arguments."""
    _fields_ = [("name", c_char_p), ("contents", c_char_p), ('length', c_ulong)]

class CompletionChunk:
    class Kind:
        def __init__(self, name):
            self.name = name

        def __str__(self):
            return self.name

        def __repr__(self):
            return "<ChunkKind: %s>" % self

    def __init__(self, completionString, key):
        self.cs = completionString
        self.key = key

    def __repr__(self):
        return "{'" + self.spelling + "', " + str(self.kind) + "}"

    @property
    def spelling(self):
        return lib.clang_getCompletionChunkText(self.cs, self.key).spelling

    @property
    def kind(self):
        res = lib.clang_getCompletionChunkKind(self.cs, self.key)
        return completionChunkKindMap[res]

    @property
    def string(self):
        res = lib.clang_getCompletionChunkCompletionString(self.cs, self.key)

        if (res):
            return CompletionString(res)
        else:
            None

    def isKindOptional(self):
        return self.kind == completionChunkKindMap[0]

    def isKindTypedText(self):
        return self.kind == completionChunkKindMap[1]

    def isKindPlaceHolder(self):
        return self.kind == completionChunkKindMap[3]

    def isKindInformative(self):
        return self.kind == completionChunkKindMap[4]

    def isKindResultType(self):
        return self.kind == completionChunkKindMap[15]

completionChunkKindMap = {
            0: CompletionChunk.Kind("Optional"),
            1: CompletionChunk.Kind("TypedText"),
            2: CompletionChunk.Kind("Text"),
            3: CompletionChunk.Kind("Placeholder"),
            4: CompletionChunk.Kind("Informative"),
            5: CompletionChunk.Kind("CurrentParameter"),
            6: CompletionChunk.Kind("LeftParen"),
            7: CompletionChunk.Kind("RightParen"),
            8: CompletionChunk.Kind("LeftBracket"),
            9: CompletionChunk.Kind("RightBracket"),
            10: CompletionChunk.Kind("LeftBrace"),
            11: CompletionChunk.Kind("RightBrace"),
            12: CompletionChunk.Kind("LeftAngle"),
            13: CompletionChunk.Kind("RightAngle"),
            14: CompletionChunk.Kind("Comma"),
            15: CompletionChunk.Kind("ResultType"),
            16: CompletionChunk.Kind("Colon"),
            17: CompletionChunk.Kind("SemiColon"),
            18: CompletionChunk.Kind("Equal"),
            19: CompletionChunk.Kind("HorizontalSpace"),
            20: CompletionChunk.Kind("VerticalSpace")}

class CompletionString(ClangObject):
    class Availability:
        def __init__(self, name):
            self.name = name

        def __str__(self):
            return self.name

        def __repr__(self):
            return "<Availability: %s>" % self

    def __len__(self):
        return lib.clang_getNumCompletionChunks(self.obj)

    def __getitem__(self, key):
        if len(self) <= key:
            raise IndexError
        return CompletionChunk(self.obj, key)

    @property
    def priority(self):
        return lib.clang_getCompletionPriority(self.obj)

    @property
    def availability(self):
        res = lib.clang_getCompletionAvailability(self.obj)
        return availabilityKinds[res]

    def __repr__(self):
        return " | ".join([str(a) for a in self]) \
               + " || Priority: " + str(self.priority) \
               + " || Availability: " + str(self.availability)

availabilityKinds = {
            0: CompletionChunk.Kind("Available"),
            1: CompletionChunk.Kind("Deprecated"),
            2: CompletionChunk.Kind("NotAvailable")}

class CodeCompletionResult(Structure):
    _fields_ = [('cursorKind', c_int), ('completionString', c_object_p)]

    def __repr__(self):
        return str(CompletionString(self.completionString))

    @property
    def kind(self):
        return CursorKind.from_value(self.cursorKind)

    @property
    def string(self):
        return CompletionString(self.completionString)

class CCRStructure(Structure):
    _fields_ = [('results', POINTER(CodeCompletionResult)),
                ('numResults', c_int)]

    def __len__(self):
        return self.numResults

    def __getitem__(self, key):
        if len(self) <= key:
            raise IndexError

        return self.results[key]

class CodeCompletionResults(ClangObject):
    def __init__(self, ptr):
        assert isinstance(ptr, POINTER(CCRStructure)) and ptr
        self.ptr = self._as_parameter_ = ptr

    def from_param(self):
        return self._as_parameter_

    def __del__(self):
        lib.clang_disposeCodeCompleteResults(self)

    @property
    def results(self):
        return self.ptr.contents

    @property
    def diagnostics(self):
        class DiagnosticsItr:
            def __init__(self, ccr):
                self.ccr = ccr

            def __len__(self):
                return int(lib.clang_codeCompleteGetNumDiagnostics(self.ccr))

            def __getitem__(self, key):
                return lib.clang_codeCompleteGetDiagnostic(self.ccr, key)

        return DiagnosticsItr(self)


class Index(ClangObject):
    """The main interface to the Clang CIndex library.

    This can be thought of as context. Every operation takes place inside a
    specific Index and all objects can be traced to one.
    """

    @staticmethod
    def create(excludeDecls=False):
        """Create a new Index.

        Parameters:
        excludeDecls -- Exclude local declarations from translation units.
        """
        return Index(lib.clang_createIndex(excludeDecls, 0))

    def __del__(self):
        lib.clang_disposeIndex(self)

    def read(self, path):
        """Load a TranslationUnit from the given AST file."""
        return TranslationUnit.from_ast(path, self)

    def parse(self, path, args=None, unsaved_files=None, options = 0):
        """Load the translation unit from the given source code file by running
        clang and generating the AST before loading. Additional command line
        parameters can be passed to clang via the args parameter.

        In-memory contents for files can be provided by passing a list of pairs
        to as unsaved_files, the first item should be the filenames to be mapped
        and the second should be the contents to be substituted for the
        file. The contents may be passed as strings or file objects.

        If an error was encountered during parsing, a TranslationUnitLoadError
        will be raised.
        """
        return TranslationUnit.from_source(path, args, unsaved_files, options,
                                           self)

class CXTUResourceUsage(Structure):
    """Represents a raw CXTUResourceUsage struct."""

    _fields_ = [('data', c_void_p),('number', c_uint),('entries', c_void_p)]

    class CXTUResourceUsageEntry(Structure):
        _fields_ = [('kind', c_uint), ('amount', c_ulong)]

    def __del__(self):
        lib.clang_disposeCXTUResourceUsage(self)

    def to_dict(self):
        """Converts the structure to a dictionary.

        Keys in the dictionary are ResourceUsageKind instances and values are
        the numeric value for that kind.
        """
        p_type = POINTER(CXTUResourceUsage.CXTUResourceUsageEntry * self.number)
        p = cast(self.entries, p_type).contents

        ret = {}
        for entry in p:
            ret[ResourceUsageKind.from_value(entry.kind)] = entry.amount

        return ret

class TranslationUnit(ClangObject):
    """Represents a source code translation unit.

    This is one of the main types in the API. Any time you wish to interact
    with Clang's representation of a source file, you typically start with a
    translation unit.
    """

    # Default parsing mode.
    PARSE_NONE = 0

    # Instruct the parser to create a detailed processing record containing
    # metadata not normally retained.
    PARSE_DETAILED_PROCESSING_RECORD = 1

    # Indicates that the translation unit is incomplete. This is typically used
    # when parsing headers.
    PARSE_INCOMPLETE = 2

    # Instruct the parser to create a pre-compiled preamble for the translation
    # unit. This caches the preamble (included files at top of source file).
    # This is useful if the translation unit will be reparsed and you don't
    # want to incur the overhead of reparsing the preamble.
    PARSE_PRECOMPILED_PREAMBLE = 4

    # Cache code completion information on parse. This adds time to parsing but
    # speeds up code completion.
    PARSE_CACHE_COMPLETION_RESULTS = 8

    # Flags with values 16 and 32 are deprecated and intentionally omitted.

    # Do not parse function bodies. This is useful if you only care about
    # searching for declarations/definitions.
    PARSE_SKIP_FUNCTION_BODIES = 64

    @classmethod
    def from_source(cls, filename, args=None, unsaved_files=None, options=0,
                    index=None):
        """Create a TranslationUnit by parsing source.

        This is capable of processing source code both from files on the
        filesystem as well as in-memory contents.

        Command-line arguments that would be passed to clang are specified as
        a list via args. These can be used to specify include paths, warnings,
        etc. e.g. ["-Wall", "-I/path/to/include"].

        In-memory file content can be provided via unsaved_files. This is an
        iterable of 2-tuples. The first element is the str filename. The
        second element defines the content. Content can be provided as str
        source code or as file objects (anything with a read() method). If
        a file object is being used, content will be read until EOF and the
        read cursor will not be reset to its original position.

        options is a bitwise or of TranslationUnit.PARSE_XXX flags which will
        control parsing behavior.

        index is an Index instance to utilize. If not provided, a new Index
        will be created for this TranslationUnit.

        To parse source from the filesystem, the filename of the file to parse
        is specified by the filename argument. Or, filename could be None and
        the args list would contain the filename(s) to parse.

        To parse source from an in-memory buffer, set filename to the virtual
        filename you wish to associate with this source (e.g. "test.c"). The
        contents of that file are then provided in unsaved_files.

        If an error occurs, a TranslationUnitLoadError is raised.

        Please note that a TranslationUnit with parser errors may be returned.
        It is the caller's responsibility to check tu.diagnostics for errors.

        Also note that Clang infers the source language from the extension of
        the input filename. If you pass in source code containing a C++ class
        declaration with the filename "test.c" parsing will fail.
        """
        if args is None:
            args = []

        if unsaved_files is None:
            unsaved_files = []

        if index is None:
            index = Index.create()

        args_array = None
        if len(args) > 0:
            args_array = (c_char_p * len(args))(* args)

        unsaved_array = None
        if len(unsaved_files) > 0:
            unsaved_array = (_CXUnsavedFile * len(unsaved_files))()
            for i, (name, contents) in enumerate(unsaved_files):
                if hasattr(contents, "read"):
                    contents = contents.read()

                unsaved_array[i].name = name
                unsaved_array[i].contents = contents
                unsaved_array[i].length = len(contents)

        ptr = lib.clang_parseTranslationUnit(index, filename, args_array,
                                             len(args), unsaved_array,
                                             len(unsaved_files), options)

        if ptr is None:
            raise TranslationUnitLoadError("Error parsing translation unit.")

        return cls(ptr, index=index)

    @classmethod
    def from_ast_file(cls, filename, index=None):
        """Create a TranslationUnit instance from a saved AST file.

        A previously-saved AST file (provided with -emit-ast or
        TranslationUnit.save()) is loaded from the filename specified.

        If the file cannot be loaded, a TranslationUnitLoadError will be
        raised.

        index is optional and is the Index instance to use. If not provided,
        a default Index will be created.
        """
        if index is None:
            index = Index.create()

        ptr = lib.clang_createTranslationUnit(index, filename)
        if ptr is None:
            raise TranslationUnitLoadError(filename)

        return cls(ptr=ptr, index=index)

    def __init__(self, ptr, index):
        """Create a TranslationUnit instance.

        TranslationUnits should be created using one of the from_* @classmethod
        functions above. __init__ is only called internally.
        """
        assert isinstance(index, Index)

        ClangObject.__init__(self, ptr)

        # We hold on to a reference to the underlying index so it won't get
        # garbage collected before us.
        self._index = index

    def __del__(self):
        lib.clang_disposeTranslationUnit(self)

    @property
    def cursor(self):
        """Retrieve the cursor that represents the given translation unit."""
        return lib.clang_getTranslationUnitCursor(self)

    @property
    def spelling(self):
        """Get the original translation unit source file name."""
        return lib.clang_getTranslationUnitSpelling(self)

    def get_includes(self):
        """
        Return an iterable sequence of FileInclusion objects that describe the
        sequence of inclusions in a translation unit. The first object in
        this sequence is always the input file. Note that this method will not
        recursively iterate over header files included through precompiled
        headers.
        """
        def visitor(fobj, lptr, depth, includes):
            if depth > 0:
                loc = SourceLocation(structure=lptr.contents, tu=self)
                includes.append(FileInclusion(loc.file, File(fobj), loc, depth))

        # Automatically adapt CIndex/ctype pointers to python objects
        includes = []
        lib.clang_getInclusions(self,
                                callbacks['translation_unit_includes'](visitor),
                                includes)
        return iter(includes)

    @property
    def diagnostics(self):
        """
        Return an iterable (and indexable) object containing the diagnostics.
        """
        class DiagIterator:
            def __init__(self, tu):
                self.tu = tu

            def __len__(self):
                return int(lib.clang_getNumDiagnostics(self.tu))

            def __getitem__(self, key):
                diag = lib.clang_getDiagnostic(self.tu, key)
                if not diag:
                    raise IndexError
                return Diagnostic(diag, tu=self.tu)

        return DiagIterator(self)

    def reparse(self, unsaved_files=None, options=0):
        """Reparse an already parsed translation unit.

        In-memory contents for files can be provided by passing a list of
        2-tuples in unsaved_files. The first item should be the filename to
        be mapped and the second should be the contents to be substituted for
        the file. The contents may be passed as strings or file objects.
        """
        if unsaved_files is None:
            unsaved_files = []

        unsaved_files_array = 0
        if len(unsaved_files):
            unsaved_files_array = (_CXUnsavedFile * len(unsaved_files))()
            for i, (name, value) in enumerate(unsaved_files):
                if not isinstance(value, str):
                    # FIXME: It would be great to support an efficient version
                    # of this, one day.
                    value = value.read()
                    print value
                if not isinstance(value, str):
                    raise TypeError('Unexpected unsaved file contents.')
                unsaved_files_array[i].name = name
                unsaved_files_array[i].contents = value
                unsaved_files_array[i].length = len(value)
        ptr = lib.clang_reparseTranslationUnit(self, len(unsaved_files),
                                               unsaved_files_array,
                                               options)

    def save(self, filename):
        """Saves the TranslationUnit to a file.

        This is equivalent to passing -emit-ast to the clang frontend. The
        saved file can be loaded back into a TranslationUnit. Or, if it
        corresponds to a header, it can be used as a pre-compiled header file.

        If an error occurs while saving, a TranslationUnitSaveError is raised.
        If the error was TranslationUnitSaveError.ERROR_INVALID_TU, this means
        the constructed TranslationUnit was not valid at time of save. In this
        case, the reason(s) why should be available via
        TranslationUnit.diagnostics().

        filename -- The path to save the translation unit to.
        """
        options = lib.clang_defaultSaveOptions(self)
        result = int(lib.clang_saveTranslationUnit(self, filename, options))
        if result != 0:
            raise TranslationUnitSaveError(result,
                'Error saving TranslationUnit.')

    def codeComplete(self, path, line, column, unsaved_files=None, options=0):
        """
        Code complete in this translation unit.

        In-memory contents for files can be provided by passing a list of pairs
        as unsaved_files, the first items should be the filenames to be mapped
        and the second should be the contents to be substituted for the
        file. The contents may be passed as strings or file objects.
        """
        if unsaved_files is None:
            unsaved_files = []

        unsaved_files_array = 0
        if len(unsaved_files):
            unsaved_files_array = (_CXUnsavedFile * len(unsaved_files))()
            for i, (name, value) in enumerate(unsaved_files):
                if not isinstance(value, str):
                    # FIXME: It would be great to support an efficient version
                    # of this, one day.
                    value = value.read()
                    print value
                if not isinstance(value, str):
                    raise TypeError('Unexpected unsaved file contents.')
                unsaved_files_array[i].name = name
                unsaved_files_array[i].contents = value
                unsaved_files_array[i].length = len(value)
        ptr = lib.clang_codeCompleteAt(self, path, line, column,
                                       unsaved_files_array, len(unsaved_files),
                                       options)
        if ptr:
            return CodeCompletionResults(ptr)
        return None

    def get_tokens(self, start_location=None, end_location=None,
                   sourcerange=None):
        """Obtain tokens in the translation unit.

        This is a generator for Token instances.

        Currently, the extraction range must be explicitly defined. This can be
        accomplished by passing both start_location and end_location. Or, pass
        sourcerange.

        start_location -- SourceLocation from which to start getting tokens.
        end_location -- SourceLocation at which to finish receiving tokens.
        sourcerange -- SourceRange to fetch tokens from.
        """
        use_range = None
        if sourcerange is not None:
            assert(isinstance(sourcerange, SourceRange))
            use_range = sourcerange
        elif start_location is not None and end_location is not None:
            use_range = SourceRange(start=start_location, end=end_location)
        else:
            raise Exception('Must supply sourcerange or locations.')

        # The allocated memory during clang_tokenize() merely holds a copy of
        # the structs. We make a copy of each array element and then release
        # the original block so Python can manage each token instance
        # independently.

        # TODO there is probably a more efficient way to copy the data without
        # having to create an original Token instance.
        memory = POINTER(Token.CXToken)()
        number = c_uint()
        lib.clang_tokenize(self, use_range.from_param(), byref(memory),
                           byref(number))

        count = int(number.value)
        tokens_p = cast(memory, POINTER(Token.CXToken * count)).contents
        tokens = [None] * count

        for i in range(0, count):
            original = tokens_p[i]
            copy = Token.CXToken()
            copy.int_data = original.int_data
            copy.ptr_data = original.ptr_data

            tokens[i] = Token(structure=copy, tu=self)

        lib.clang_disposeTokens(self, memory, number)

        for token in tokens:
            yield token

    @property
    def resource_usage(self):
        """Obtain the resource usage for the Translation Unit.

        Returns a dictionary of strings to ints where the keys correspond to
        the resource name.
        """
        resource = lib.clang_getCXTUResourceUsage(self)
        return resource.to_dict()

class File(ClangObject):
    """
    The File class represents a particular source file that is part of a
    translation unit.
    """

    __slots__ = ('_tu')

    def __init__(self, obj):
        ClangObject.__init__(self, obj)
        self._tu = None

    @staticmethod
    def from_name(translation_unit, file_name):
        """Retrieve a file handle within the given translation unit."""
        f = File(lib.clang_getFile(translation_unit, file_name))
        f._tu = translation_unit

        return f

    @staticmethod
    def from_cursor_result(res, func, args):
        assert isinstance(res, File)

        # Copy a reference to the TranslationUnit to prevent premature GC.
        res._tu = args[0]._tu
        return res

    @property
    def name(self):
        """Return the complete file and path name of the file."""
        return lib.clang_getFileName(self)

    @property
    def time(self):
        """Return the last modification time of the file."""
        return lib.clang_getFileTime(self)

    @property
    def is_multiple_include_guarded(self):
        """Return whether this file is guarded against multiple inclusions."""
        return lib.clang_isFileMultipleIncludeGuarded(self._tu, self)

    @property
    def translation_unit(self):
        """Return the TranslationUnit to which this File belongs."""
        return self._tu

    def __str__(self):
        return self.name

    def __repr__(self):
        return "<File: %s>" % (self.name)

class FileInclusion(object):
    """
    The FileInclusion class represents the inclusion of one source file by
    another via a '#include' directive or as the input file for the translation
    unit. This class provides information about the included file, the including
    file, the location of the '#include' directive and the depth of the included
    file in the stack. Note that the input file has depth 0.
    """

    def __init__(self, src, tgt, loc, depth):
        self.source = src
        self.include = tgt
        self.location = loc
        self.depth = depth

    @property
    def is_input_file(self):
        """True if the included file is the input file."""
        return self.depth == 0

# Now comes the plumbing to hook up the C library.

# Register callback types in common container.
callbacks['translation_unit_includes'] = CFUNCTYPE(None, c_object_p,
        POINTER(SourceLocation.CXSourceLocation), c_uint, py_object)
callbacks['cursor_visit'] = CFUNCTYPE(c_int, Cursor.CXCursor, Cursor.CXCursor,
                                      py_object)

def register_functions(lib):
    """Register function prototypes with a libclang library instance.

    This must be called as part of library instantiation so Python knows how
    to call out to the shared library.
    """
    # Functions are registered in strictly alphabetical order.
    lib.clang_annotateTokens.argtype = [TranslationUnit, POINTER(Token.CXToken),
                                        c_uint, POINTER(Cursor.CXCursor)]

    lib.clang_codeCompleteAt.argtypes = [TranslationUnit, c_char_p, c_int,
            c_int, c_void_p, c_int, c_int]
    lib.clang_codeCompleteAt.restype = POINTER(CCRStructure)

    lib.clang_codeCompleteGetDiagnostic.argtypes = [CodeCompletionResults,
            c_int]
    lib.clang_codeCompleteGetDiagnostic.restype = Diagnostic

    lib.clang_codeCompleteGetNumDiagnostics.argtypes = [CodeCompletionResults]
    lib.clang_codeCompleteGetNumDiagnostics.restype = c_int

    lib.clang_createIndex.argtypes = [c_int, c_int]
    lib.clang_createIndex.restype = c_object_p

    lib.clang_createTranslationUnit.argtypes = [Index, c_char_p]
    lib.clang_createTranslationUnit.restype = c_object_p

    lib.clang_Cursor_isNull.argtypes = [Cursor.CXCursor]
    lib.clang_Cursor_isNull.restype = bool

    lib.clang_CXXMethod_isStatic.argtypes = [Cursor.CXCursor]
    lib.clang_CXXMethod_isStatic.restype = bool

    lib.clang_CXXMethod_isVirtual.argtypes = [Cursor.CXCursor]
    lib.clang_CXXMethod_isVirtual.restype = bool

    lib.clang_defaultSaveOptions.argtypes = [TranslationUnit]
    lib.clang_defaultSaveOptions.restype = c_uint

    lib.clang_disposeCodeCompleteResults.argtypes = [CodeCompletionResults]

    lib.clang_disposeCXTUResourceUsage.argtypes = [CXTUResourceUsage]

    lib.clang_disposeDiagnostic.argtypes = [Diagnostic]

    lib.clang_disposeIndex.argtypes = [Index]

    lib.clang_disposeString.argtypes = [CXString]

    lib.clang_disposeTokens.argtype = [TranslationUnit, POINTER(Token.CXToken),
                                      c_uint]

    lib.clang_disposeTranslationUnit.argtypes = [TranslationUnit]

    lib.clang_equalCursors.argtypes = [Cursor.CXCursor, Cursor.CXCursor]
    lib.clang_equalCursors.restype = bool

    lib.clang_equalLocations.argtypes = [SourceLocation.CXSourceLocation,
                                         SourceLocation.CXSourceLocation]
    lib.clang_equalLocations.restype = bool

    lib.clang_equalRanges.argtypes = [SourceRange.CXSourceRange,
                                      SourceRange.CXSourceRange]
    lib.clang_equalRanges.restype = bool

    lib.clang_equalTypes.argtypes = [Type.CXType, Type.CXType]
    lib.clang_equalTypes.restype = bool

    lib.clang_getArgType.argtypes = [Type.CXType, c_uint]
    lib.clang_getArgType.restype = Type.CXType
    lib.clang_getArgType.errcheck = Type.from_struct

    lib.clang_getArrayElementType.argtypes = [Type.CXType]
    lib.clang_getArrayElementType.restype = Type.CXType
    lib.clang_getArrayElementType.errcheck = Type.from_struct

    lib.clang_getArraySize.argtypes = [Type.CXType]
    lib.clang_getArraySize.restype = c_longlong

    lib.clang_getCanonicalCursor.argtypes = [Cursor.CXCursor]
    lib.clang_getCanonicalCursor.restype = Cursor.CXCursor
    lib.clang_getCanonicalCursor.errcheck = Cursor.from_struct

    lib.clang_getCanonicalType.argtypes = [Type.CXType]
    lib.clang_getCanonicalType.restype = Type.CXType
    lib.clang_getCanonicalType.errcheck = Type.from_struct

    lib.clang_getCompletionAvailability.argtypes = [c_void_p]
    lib.clang_getCompletionAvailability.restype = c_int

    lib.clang_getCompletionChunkCompletionString.argtypes = [c_void_p, c_int]
    lib.clang_getCompletionChunkCompletionString.restype = c_object_p

    lib.clang_getCompletionChunkKind.argtypes = [c_void_p, c_int]
    lib.clang_getCompletionChunkKind.restype = c_int

    lib.clang_getCompletionChunkText.argtypes = [c_void_p, c_int]
    lib.clang_getCompletionChunkText.restype = CXString

    lib.clang_getCompletionPriority.argtypes = [c_void_p]
    lib.clang_getCompletionPriority.restype = c_int

    lib.clang_getCString.argtypes = [CXString]
    lib.clang_getCString.restype = c_char_p

    lib.clang_getCursor.argtypes = [TranslationUnit,
                                    SourceLocation.CXSourceLocation]
    lib.clang_getCursor.restype = Cursor.CXCursor
    # errcheck not defined because this is called directly from Cursor()
    # constructor.

    lib.clang_getCursorDefinition.argtypes = [Cursor.CXCursor]
    lib.clang_getCursorDefinition.restype = Cursor.CXCursor
    lib.clang_getCursorDefinition.errcheck = Cursor.from_struct

    lib.clang_getCursorDisplayName.argtypes = [Cursor.CXCursor]
    lib.clang_getCursorDisplayName.restype = CXString
    lib.clang_getCursorDisplayName.errcheck = CXString.from_result

    lib.clang_getCursorExtent.argtypes = [Cursor.CXCursor]
    lib.clang_getCursorExtent.restype = SourceRange.CXSourceRange
    lib.clang_getCursorExtent.errcheck = SourceRange.from_struct

    lib.clang_getCursorLexicalParent.argtypes = [Cursor.CXCursor]
    lib.clang_getCursorLexicalParent.restype = Cursor.CXCursor
    lib.clang_getCursorLexicalParent.errcheck = Cursor.from_struct

    lib.clang_getCursorLocation.argtypes = [Cursor.CXCursor]
    lib.clang_getCursorLocation.restype = SourceLocation.CXSourceLocation
    lib.clang_getCursorLocation.errcheck = SourceLocation.from_struct

    lib.clang_getCursorReferenced.argtypes = [Cursor.CXCursor]
    lib.clang_getCursorReferenced.restype = Cursor.CXCursor
    lib.clang_getCursorReferenced.errcheck = Cursor.from_struct

    lib.clang_getCursorReferenceNameRange.argtypes = [Cursor.CXCursor, c_uint,
                                                     c_uint]
    lib.clang_getCursorReferenceNameRange.restype = SourceRange.CXSourceRange
    lib.clang_getCursorReferenceNameRange.errcheck = SourceRange.from_struct

    lib.clang_getCursorSemanticParent.argtypes = [Cursor.CXCursor]
    lib.clang_getCursorSemanticParent.restype = Cursor.CXCursor
    lib.clang_getCursorSemanticParent.errcheck = Cursor.from_struct

    lib.clang_getCursorSpelling.argtypes = [Cursor.CXCursor]
    lib.clang_getCursorSpelling.restype = CXString
    lib.clang_getCursorSpelling.errcheck = CXString.from_result

    lib.clang_getCursorType.argtypes = [Cursor.CXCursor]
    lib.clang_getCursorType.restype = Type.CXType
    lib.clang_getCursorType.errcheck = Type.from_struct

    lib.clang_getCursorUSR.argtypes = [Cursor.CXCursor]
    lib.clang_getCursorUSR.restype = CXString
    lib.clang_getCursorUSR.errcheck = CXString.from_result

    lib.clang_getCXTUResourceUsage.argtypes = [TranslationUnit]
    lib.clang_getCXTUResourceUsage.restype = CXTUResourceUsage

    lib.clang_getCXXAccessSpecifier.argtypes = [Cursor.CXCursor]
    lib.clang_getCXXAccessSpecifier.restype = c_uint

    lib.clang_getDeclObjCTypeEncoding.argtypes = [Cursor.CXCursor]
    lib.clang_getDeclObjCTypeEncoding.restype = CXString
    lib.clang_getDeclObjCTypeEncoding.errcheck = CXString.from_result

    lib.clang_getDiagnostic.argtypes = [c_object_p, c_uint]
    lib.clang_getDiagnostic.restype = c_object_p

    lib.clang_getDiagnosticCategory.argtypes = [Diagnostic]
    lib.clang_getDiagnosticCategory.restype = c_uint

    lib.clang_getDiagnosticCategoryName.argtypes = [c_uint]
    lib.clang_getDiagnosticCategoryName.restype = CXString
    lib.clang_getDiagnosticCategoryName.errcheck = CXString.from_result

    lib.clang_getDiagnosticFixIt.argtypes = [Diagnostic, c_uint,
            POINTER(SourceRange.CXSourceRange)]
    lib.clang_getDiagnosticFixIt.restype = CXString
    lib.clang_getDiagnosticFixIt.errcheck = CXString.from_result

    lib.clang_getDiagnosticLocation.argtypes = [Diagnostic]
    lib.clang_getDiagnosticLocation.restype = SourceLocation.CXSourceLocation
    lib.clang_getDiagnosticLocation.errcheck = SourceLocation.from_struct

    lib.clang_getDiagnosticNumFixIts.argtypes = [Diagnostic]
    lib.clang_getDiagnosticNumFixIts.restype = c_uint

    lib.clang_getDiagnosticNumRanges.argtypes = [Diagnostic]
    lib.clang_getDiagnosticNumRanges.restype = c_uint

    lib.clang_getDiagnosticOption.argtypes = [Diagnostic, POINTER(CXString)]
    lib.clang_getDiagnosticOption.restype = CXString
    lib.clang_getDiagnosticOption.errcheck = CXString.from_result

    lib.clang_getDiagnosticRange.argtypes = [Diagnostic, c_uint]
    lib.clang_getDiagnosticRange.restype = SourceRange.CXSourceRange
    lib.clang_getDiagnosticRange.errcheck = SourceRange.from_struct

    lib.clang_getDiagnosticSeverity.argtypes = [Diagnostic]
    lib.clang_getDiagnosticSeverity.restype = c_int

    lib.clang_getDiagnosticSpelling.argtypes = [Diagnostic]
    lib.clang_getDiagnosticSpelling.restype = CXString
    lib.clang_getDiagnosticSpelling.errcheck = CXString.from_result

    lib.clang_getElementType.argtypes = [Type.CXType]
    lib.clang_getElementType.restype = Type.CXType
    lib.clang_getElementType.errcheck = Type.from_struct

    lib.clang_getEnumDeclIntegerType.argtypes = [Cursor.CXCursor]
    lib.clang_getEnumDeclIntegerType.restype = Type.CXType
    lib.clang_getEnumDeclIntegerType.errcheck = Type.from_struct

    lib.clang_getExpansionLocation.argtypes = [SourceLocation.CXSourceLocation,
            POINTER(c_object_p), POINTER(c_uint), POINTER(c_uint),
            POINTER(c_uint)]
    lib.clang_getExpansionLocation.restype = None

    lib.clang_getFile.argtypes = [TranslationUnit, c_char_p]
    lib.clang_getFile.restype = c_object_p

    lib.clang_getFileName.argtypes = [File]
    lib.clang_getFileName.restype = CXString
    lib.clang_getFileName.errcheck = CXString.from_result

    lib.clang_getFileTime.argtypes = [File]
    lib.clang_getFileTime.restype = c_uint

    lib.clang_getIBOutletCollectionType.argtypes = [Cursor.CXCursor]
    lib.clang_getIBOutletCollectionType.restype = Type.CXType
    lib.clang_getIBOutletCollectionType.errcheck = Type.from_struct

    lib.clang_getIncludedFile.argtypes = [Cursor.CXCursor]
    lib.clang_getIncludedFile.restype = File
    lib.clang_getIncludedFile.errcheck = File.from_cursor_result

    lib.clang_getInclusions.argtypes = [TranslationUnit,
            callbacks['translation_unit_includes'], py_object]

    lib.clang_getLocation.argtypes = [TranslationUnit, File, c_uint, c_uint]
    lib.clang_getLocation.restype = SourceLocation.CXSourceLocation
    # errcheck omitted because this is called only by SourceLocation's
    # constructor.

    lib.clang_getLocationForOffset.argtypes = [TranslationUnit, File, c_uint]
    lib.clang_getLocationForOffset.restype = SourceLocation.CXSourceLocation
    # errcheck omitted because this is called only by SourceLocation's
    # constructor.

    lib.clang_getNullCursor.restype = Cursor.CXCursor

    lib.clang_getNumArgTypes.argtypes = [Type.CXType]
    lib.clang_getNumArgTypes.restype = c_uint

    lib.clang_getNumCompletionChunks.argtypes = [c_void_p]
    lib.clang_getNumCompletionChunks.restype = c_int

    lib.clang_getNumDiagnostics.argtypes = [c_object_p]
    lib.clang_getNumDiagnostics.restype = c_uint

    lib.clang_getNumElements.argtypes = [Type.CXType]
    lib.clang_getNumElements.restype = c_longlong

    lib.clang_getNumOverloadedDecls.argtypes = [Cursor.CXCursor]
    lib.clang_getNumOverloadedDecls.restyp = c_uint

    lib.clang_getOverloadedDecl.argtypes = [Cursor.CXCursor, c_uint]
    lib.clang_getOverloadedDecl.restype = Cursor.CXCursor
    lib.clang_getOverloadedDecl.errcheck = Cursor.from_struct

    lib.clang_getPointeeType.argtypes = [Type.CXType]
    lib.clang_getPointeeType.restype = Type.CXType
    lib.clang_getPointeeType.errcheck = Type.from_struct

    lib.clang_getPresumedLocation.argtypes = [SourceLocation.CXSourceLocation,
                                              POINTER(c_object_p),
                                              POINTER(c_uint),
                                              POINTER(c_uint)]
    lib.clang_getPresumedLocation.restype = None

    lib.clang_getRange.argtypes = [SourceLocation.CXSourceLocation,
                                   SourceLocation.CXSourceLocation]
    lib.clang_getRange.restype = SourceRange.CXSourceRange
    # errcheck omitted because called from SourceRange constructor.

    lib.clang_getRangeEnd.argtypes = [SourceRange.CXSourceRange]
    lib.clang_getRangeEnd.restype = SourceLocation.CXSourceLocation
    lib.clang_getRangeEnd.errcheck = SourceLocation.from_struct

    lib.clang_getRangeStart.argtypes = [SourceRange.CXSourceRange]
    lib.clang_getRangeStart.restype = SourceLocation.CXSourceLocation
    lib.clang_getRangeStart.errcheck = SourceLocation.from_struct

    lib.clang_getResultType.argtypes = [Type.CXType]
    lib.clang_getResultType.restype = Type.CXType
    lib.clang_getResultType.errcheck = Type.from_struct

    lib.clang_getSpecializedCursorTemplate.argtypes = [Cursor.CXCursor]
    lib.clang_getSpecializedCursorTemplate.restype = Cursor.CXCursor
    lib.clang_getSpecializedCursorTemplate.errcheck = Cursor.from_struct

    lib.clang_getSpellingLocation.argtypes = [SourceLocation.CXSourceLocation,
                                              POINTER(c_object_p),
                                              POINTER(c_uint),
                                              POINTER(c_uint),
                                              POINTER(c_uint)]
    lib.clang_getSpellingLocation.restype = None

    lib.clang_getTemplateCursorKind.argtypes = [Cursor.CXCursor]
    lib.clang_getTemplateCursorKind.restype = c_uint

    lib.clang_getTokenExtent.argtypes = [TranslationUnit, Token.CXToken]
    lib.clang_getTokenExtent.restype = SourceRange.CXSourceRange
    lib.clang_getTokenExtent.errcheck = SourceRange.from_struct

    lib.clang_getTokenKind.argtypes = [Token.CXToken]
    lib.clang_getTokenKind.restype = c_uint

    lib.clang_getTokenLocation.argtype = [TranslationUnit, Token.CXToken]
    lib.clang_getTokenLocation.restype = SourceLocation.CXSourceLocation
    lib.clang_getTokenLocation.errcheck = SourceLocation.from_struct

    lib.clang_getTokenSpelling.argtype = [TranslationUnit, Token.CXToken]
    lib.clang_getTokenSpelling.restype = CXString
    lib.clang_getTokenSpelling.errcheck = CXString.from_result

    lib.clang_getTranslationUnitCursor.argtypes = [TranslationUnit]
    lib.clang_getTranslationUnitCursor.restype = Cursor.CXCursor
    lib.clang_getTranslationUnitCursor.errcheck = Cursor.from_struct

    lib.clang_getTranslationUnitSpelling.argtypes = [TranslationUnit]
    lib.clang_getTranslationUnitSpelling.restype = CXString
    lib.clang_getTranslationUnitSpelling.errcheck = CXString.from_result

    lib.clang_getTUResourceUsageName.argtypes = [c_uint]
    lib.clang_getTUResourceUsageName.restype = c_char_p

    lib.clang_getTypeDeclaration.argtypes = [Type.CXType]
    lib.clang_getTypeDeclaration.restype = Cursor.CXCursor
    lib.clang_getTypeDeclaration.errcheck = Cursor.from_struct

    lib.clang_getTypedefDeclUnderlyingType.argtypes = [Cursor.CXCursor]
    lib.clang_getTypedefDeclUnderlyingType.restype = Type.CXType
    lib.clang_getTypedefDeclUnderlyingType.errcheck = Type.from_struct

    lib.clang_getTypeKindSpelling.argtypes = [c_uint]
    lib.clang_getTypeKindSpelling.restype = CXString
    lib.clang_getTypeKindSpelling.errcheck = CXString.from_result

    lib.clang_hashCursor.argtypes = [Cursor.CXCursor]
    lib.clang_hashCursor.restype = c_uint

    lib.clang_isAttribute.argtypes = [CursorKind]
    lib.clang_isAttribute.restype = bool

    lib.clang_isConstQualifiedType.argtypes = [Type.CXType]
    lib.clang_isConstQualifiedType.restype = bool

    lib.clang_isCursorDefinition.argtypes = [Cursor.CXCursor]
    lib.clang_isCursorDefinition.restype = bool

    lib.clang_isDeclaration.argtypes = [CursorKind]
    lib.clang_isDeclaration.restype = bool

    lib.clang_isExpression.argtypes = [CursorKind]
    lib.clang_isExpression.restype = bool

    lib.clang_isFileMultipleIncludeGuarded.argtypes = [TranslationUnit, File]
    lib.clang_isFileMultipleIncludeGuarded.restype = bool

    lib.clang_isFunctionTypeVariadic.argtypes = [Type.CXType]
    lib.clang_isFunctionTypeVariadic.restype = bool

    lib.clang_isInvalid.argtypes = [CursorKind]
    lib.clang_isInvalid.restype = bool

    lib.clang_isPODType.argtypes = [Type.CXType]
    lib.clang_isPODType.restype = bool

    lib.clang_isPreprocessing.argtypes = [CursorKind]
    lib.clang_isPreprocessing.restype = bool

    lib.clang_isReference.argtypes = [CursorKind]
    lib.clang_isReference.restype = bool

    lib.clang_isRestrictQualifiedType.argtypes = [Type.CXType]
    lib.clang_isRestrictQualifiedType.restype = bool

    lib.clang_isStatement.argtypes = [CursorKind]
    lib.clang_isStatement.restype = bool

    lib.clang_isTranslationUnit.argtypes = [CursorKind]
    lib.clang_isTranslationUnit.restype = bool

    lib.clang_isUnexposed.argtypes = [CursorKind]
    lib.clang_isUnexposed.restype = bool

    lib.clang_isVirtualBase.argtypes = [Cursor.CXCursor]
    lib.clang_isVirtualBase.restype = bool

    lib.clang_isVolatileQualifiedType.argtypes = [Type.CXType]
    lib.clang_isVolatileQualifiedType.restype = bool

    lib.clang_parseTranslationUnit.argypes = [Index, c_char_p, c_void_p, c_int,
            c_void_p, c_int, c_int]
    lib.clang_parseTranslationUnit.restype = c_object_p

    lib.clang_reparseTranslationUnit.argtypes = [TranslationUnit, c_int,
            c_void_p, c_int]
    lib.clang_reparseTranslationUnit.restype = c_int

    lib.clang_saveTranslationUnit.argtypes = [TranslationUnit, c_char_p,
            c_uint]
    lib.clang_saveTranslationUnit.restype = c_int

    lib.clang_tokenize.argtypes = [TranslationUnit, SourceRange.CXSourceRange,
            POINTER(POINTER(Token.CXToken)), POINTER(c_uint)]

    lib.clang_visitChildren.argtypes = [Cursor.CXCursor, callbacks['cursor_visit'],
            py_object]
    lib.clang_visitChildren.restype = c_uint

register_functions(lib)

for name, value in enumerations.CursorKinds:
    CursorKind.register(value, name)

for label, value in enumerations.CXXAccessSpecifiers:
    CXXAccessSpecifier.register(value, label)

for name, value in enumerations.TokenKinds:
    TokenKind.register(value, name)

for name, value in enumerations.TypeKinds:
    TypeKind.register(value, name)

for value, name in enumerations.ResourceUsageKinds:
    ResourceUsageKind.register(value, name)

__all__ = [
    'CodeCompletionResults',
    'CursorKind',
    'Cursor',
    'CXXAccessSpecifier',
    'Diagnostic',
    'File',
    'FixIt',
    'Index',
    'SourceLocation',
    'SourceRange',
    'Token',
    'TokenKind',
    'TranslationUnitLoadError',
    'TranslationUnit',
    'TypeKind',
    'Type',
]
