/*===-- clang-c/Compiler.h - Compiler Public C Interface-----------*- C -*-===*\
|*                                                                            *|
|*                     The LLVM Compiler Infrastructure                       *|
|*                                                                            *|
|* This file is distributed under the University of Illinois Open Source      *|
|* License. See LICENSE.TXT for details.                                      *|
|*                                                                            *|
|*===----------------------------------------------------------------------===*|
|*                                                                            *|
|* This header provides a public inferface to a Clang library for invoking    *|
|* the Clang compiler.                                                        *|
|*                                                                            *|
\*===----------------------------------------------------------------------===*/

/*
This file contains a proposal for the implementation of a C interface to the
compiler API.

Configuration of the compiler is performed by feeding in command-line
arguments. We avoid exposing the low-level *Options classes directly because
the Clang API changes frequently and people in #llvm felt that maintaining the
coupling between these low-level APIs and libclang would be a lot of ongoing
work. There is overhead in parsing these arguments all the time. It is tempting
to add APIs to copy CCompilerInvocation instances and merge new arguments into
instances. This would allow sharing of similar configuration sets without the
overhead of always reparsing all the arguments. However, the Parse*Args
functions in CompilerInvocation.cpp currently overwrite all arguments. So,
merging is unsupported. Supporting merging would require significant
refactoring there and that is currently beyond the scope of this project.

Feedback wanted:

 * Should CompilerInvocation and CompilerInstance be consolidated? Today, it
   does seem to make sense, with there being very few functions operating on
   CCCompilerInvocation that warrant a separate type. However, it may not
   always be this way and CCompilerInvocation could grow to support more
   features. At that time, it would be more compelling to split the
   functionality. Should we design for the future?

 * Split up Index.h? There are a number of entities in Index.h that can be
   shared across the various C APIs (e.g. strings, source location,
   diagnostics). Given it doesn't make sense for compiler functionality to
   exist in Index.h (or maybe it does), is it time to move things into separate
   per-component includes (or at least moving shared components to a shared
   header)?

*/

#ifndef CLANG_C_COMPILER_H
#define CLANG_C_COMPILER_H

#include "Index.h"

#ifdef __cplusplus
extern "C" {
#endif

/* MSVC DLL import/export. */
/* TODO Should this boilerplate be consolidated with Index.h? */
#ifdef _MSC_VER
  #ifdef _CCOMPILER_LIB_
    #define CCOMPILER_LINKAGE __declspec(dllexport)
  #else
    #define CCOMPILER_LINKAGE __declspec(dllimport)
  #endif
#else
  #define CCOMPILER_LINKAGE
#endif

/** \defgroup CCOMPILER libclang: C Interface to Clang Compiler
 *
 * @{
 */

/**
 * \defgroup CCOMPILER_INVOCATION Control how the compiler is invoked.
 */

/**
 * \brief Holds data necessary to invoke the compiler.
 *
 * Instances of this tell the compiler what to do. For every distinct
 * action performed by the compiler, you will need a unique instance of this
 * type.
 */
typedef void *CCCompilerInvocation;

/**
 * \brief Create a compiler invocation given command-line arguments.
 *
 * clang_disposeCompilerInvocation should be called for every produced
 * CCompilerInvocation or a memory leak will occur.
 *
 * \param num_clang_command_line_args The number of elements in
 * \pclang_command_line_args.
 *
 * \param clang_command_line_args The command-line arguments that would be
 * passed to the \c clang -cc1 executable if it were being invoked as a
 * standalone process. These arguments will be parsed and will affect how the
 * compiler runs.
 */
CCOMPILER_LINKAGE CCCompilerInvocation clang_createCompilerInvocation(
                             int num_clang_command_line_args,
                             const char * const char *clang_command_line_args);

/**
 * \brief Destroy the specified CCompilerInvocation instance.
 *
 * This should be called for each CCompilerInvocation produced by
 clang_createCompilerInvocation.
 */
CCOMPILER_LINKAGE void clang_disposeCompilerInvocation(CCCompilerInvocation i);

/**
 * TODO Support API for supplementing default resource path
 *
 * As it currently stands, *all* paths would need to be given in the
 * arguments. People shouldn't have to worry about where the system include
 * paths are, so we should expose a way to easily add these to the
 * CCompilerInvocation instance. Unfortunately, I'm not sure the best way to
 * expose this through the C API since CompilerInvocation::GetResourcesPath()
 * wants the Clang executable's path as an argument.
 */

/**
 * @}
 */

/**
 * \defgroup CCOMPILER_INSTANCE Interact with individual compiler executions.
 */

/**
 * \brief Represents a single instance of the Clang compiler.
 */
typedef void *CCCompilerInstance;

/**
 * \brief Create a compiler from invocation settings.
 *
 *
 */
CCOMPILER_LINKAGE CCCompilerInstance clang_createCompiler(CCCompilerInvocation);

/**
 * \brief Destroy an individual compiler instance.
 *
 * This should be called for every instance produced by clang_createCompiler.
 *
 * \param Instance to destroy.
 */
CCOMPILER_LINKAGE void clang_diposeCompiler(CCCompilerInstance compiler);

/**
 * \brief Execute the configured action on a compiler instance.
 *
 * \param compiler Compiler instance to run.
 *
 * \returns 0 if the compiler executed without error. A non-zero value will be
 * returned if the compiler did not execute fully and successfully.
 */
CCOMPILER_LINKAGE int clang_executeCompiler(CCCompilerInstance compiler);

/**
 * \brief Retrieve the complete set of diagnostics associated with a compiler
 *        instance.
 *
 * The returned object and its descendents have a lifetime of the compiler
 * instance they are associated with. If the compiler instance is disposed,
 * all associated diagnostics are also disposed.
 */
CCOMPILER_LINKAGE CXDiagnosticSet clang_getDiagnosticSetFromCompiler(
                                                  CCCompilerInstance compiler);

/**
 * @}
 */

/* CCOMPILER group */
/**
 * @}
 */

#ifdef __cplusplus
}
#endif
#endif