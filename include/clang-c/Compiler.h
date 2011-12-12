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

#ifndef CLANG_C_COMPILER_H
#define CLANG_C_COMPILER_H

#include "common.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * \defgroup CCOMPILER High-level Compiler Interface
 * \ingroup CLANGC
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
CLANGC_LINKAGE CCCompilerInvocation clang_createCompilerInvocation(
                             int num_clang_command_line_args,
                             const char * const char *clang_command_line_args);

/**
 * \brief Destroy the specified CCompilerInvocation instance.
 *
 * This should be called for each CCompilerInvocation produced by
 clang_createCompilerInvocation.
 */
CLANGC_LINKAGE void clang_disposeCompilerInvocation(CCCompilerInvocation i);

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
 *
 * The functions in this group form a very high-level API into the compiler.
 * Any possible compiler action can be taken. However, there is a very limited
 * ability to inspect the results.
 *
 * This API is effectively executing clang -cc1 without spawning a new process.
 */

/**
 * \brief Represents a single instance of the Clang compiler.
 */
typedef void *CCCompilerInstance;

/**
 * \brief Create a compiler from invocation settings.
 *
 * \param invocation Invocation settings to use to create compiler.
 */
CLANGC_LINKAGE CCCompilerInstance clang_createCompiler(
                                              CCCompilerInvocation invocation);

/**
 * \brief Destroy an individual compiler instance.
 *
 * This should be called for every instance produced by clang_createCompiler.
 *
 * \param Instance to destroy.
 */
CLANGC_LINKAGE void clang_diposeCompiler(CCCompilerInstance compiler);

/**
 * \brief Execute the configured action on a compiler instance.
 *
 * \param compiler Compiler instance to run.
 *
 * \returns 0 if the compiler executed without error. A non-zero value will be
 * returned if the compiler did not execute fully and successfully.
 */
CLANGC_LINKAGE int clang_executeCompiler(CCCompilerInstance compiler);

/**
 * \brief Retrieve the complete set of diagnostics associated with a compiler
 *        instance.
 *
 * The returned object and its descendents have a lifetime of the compiler
 * instance they are associated with. If the compiler instance is disposed,
 * all associated diagnostics are also disposed.
 */
CLANGC_LINKAGE CXDiagnosticSet clang_getDiagnosticSetFromCompiler(
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