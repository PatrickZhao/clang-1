/*===-- clang-c/Compiler.h - Compiler Public C Interface-----------*- C -*-===*\
|*                                                                            *|
|*                     The LLVM Compiler Infrastructure                       *|
|*                                                                            *|
|* This file is distributed under the University of Illinois Open Source      *|
|* License. See LICENSE.TXT for details.                                      *|
|*                                                                            *|
|*===----------------------------------------------------------------------===*|
|*                                                                            *|
|* This header defines a C interface to the code generation functionality of  *|
|* the Clang compiler.                                                        *|
|*                                                                            *|
\*===----------------------------------------------------------------------===*/

#ifndef CLANG_C_CODEGEN_H
#define CLANG_C_CODEGEN_H

#include "common.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * \defgroup CCODEGEN Compiler code generation
 *
 * This interfaces allows you to interact with the compiler's code generation
 * facilities. With it, you can emit assembly, LLVM bitcode, native object
 * files, and other actions supported by the CodeGenAction classes.
 *
 * The functionality in this interface is effectively a wrapper around
 * llvm::clang::CodeGenAction and llvm::clang::EmitBackendOutput().
 *
 * Data types in this module are prefixed with "CG" and functions are prefixed
 * with "clang_codegen_".
 *
 * Code generation involves the following steps:
 *
 *  -# Create a CGInput instance representing the thing you wish to create
 *     output from. See clang_codegen_createInputFromFile() and
 *     clang_codegen_createInputFromBuffer().
 *  -# Create a CGOptions instance representing how you want to transform the
 *     input. See clang_codegen_createOptionsFromArguments().
 *  -# Create the output, a CGResult instance. See
 *     clang_codegen_generateOutput().
 *  -# Validate that output was generated without error.
 *  -# Do something with your output.
 *  -# Dispose of your CGResult, CGOptions, and CGInput instances.
 *
 * @{
 */

/**
 * \brief Input type for code generation.
 *
 * Instances of these are constructed by reading from files or from loading
 * buffers. Once created, they are fed into the code generator to produce
 * output.
 *
 * Instances are produced by calling one of the clang_codegen_createInputFrom*
 * functions. Each instance must be disposed by calling
 * clang_codegen_disposeInput() or you will leak memory.
 *
 * This is veiled wrapper around llvm::Module instances.
 */
typedef void *CGInput;

/**
 * \brief Create an input object from the contents of a file.
 *
 * \param filename Path to file to load and produce output from.
 */
CLANGC_LINKAGE CGInput clang_codegen_createInputFromFile(
                                                        const char * filename);

/**
 * \brief Create an input object from the contents of a string buffer.
 *
 * The contents of the buffer are copied into the returned object. Ownership
 * of the passed memory is not transferred to the returned object.
 *
 * \param start Memory location of the beginning of the buffer
 * \param size Size of the buffer
 */
CLANGC_LINKAGE CGInput clang_codegen_createInputFromBuffer(const char *start,
                                                                size_t size);

/**
 * \brief Dispose of a created code generation input object.
 *
 * This must be called for every call to clang_codegen_createInputFromFile and
 * clang_codegen_createInputFromBuffer or you will leak memory.
 *
 * \param input The input instance to dispose.
 */
CLANGC_LINKAGE void clang_codegen_disposeInput(CGInput input);

/**
 * \brief Options to control code generation.
 */
typedef void *CGOptions;

/**
 * \brief Create code generation options from command-line arguments.
 *
 * This takes a set of arguments which you would pass to clang -cc1 and
 * converts them to an object that the compiler uses to control code
 * generation.
 *
 * Arguments controlling the input and output files are ignored because
 * functionality is provided by the API.
 *
 * clang_codegen_disposeOptions() must be called for every CGOptions produced
 * through this function or a memory leak will occur.
 *
 * It is valid to use the same CGOptions instance for multiple invocations
 * of clang_codegen_createOutput().
 *
 * \param num_arguments The number of arguments being passed in.
 * \param arguments Command-line arguments to parse to control code generation.
 */
CLANGC_LINKAGE CGOptions clang_codegen_createOptionsFromArguments(
                                                              int num_arguments,
                                           const char * const char * arguments);

/**
 * \brief Dispose of an options instance.
 *
 * This must be called for every created CGOptions instance or a memory leak
 * will occur.
 *
 * \param options The instance to dipose of.
 */
CLANGC_LINKAGE CGOptions clang_codegen_disposeOptions(CGOptions options);

/**
 * \brief Describes the code generation action to perform.
 *
 * These map to clang::BackendAction values.
 */
enum CGAction {
  /** Emit assembly files for the configured target type [-S] */
  CGAction_EmitAssembly,

  /** Emit LLVM bitcode files [-emit-llvm-bc] */
  CGAction_EmitBC,

  /** Emit human-readable LLVM assembly [-emit-llvm] */
  CGAction_EmitLL,

  /** Do work but don't actually emit anything [-emit-llvm-only] */
  CGAction_EmitNothing,

  /** Run code generation, but don't emit anything [-emit-codegen-only] */
  CGAction_EmitMCNull,

  /** Emit native object files [-emit-obj] */
  CGAction_EmitObj
};

/**
 * \brief Represents the output of a code generation invocations.
 */
typedef void *CGGenerationResult;

/**
 * \brief Perform output code generation.
 *
 * This is the function that does the heavy lifting and transforms your input
 * object into something else.
 *
 * The input object is not mutated as part of the call. Therefore, it is
 * possible to call this function multiple times on the same CGInput instance.
 *
 * The result object must be disposed by calling clang_codegen_disposeResult()
 * or a memory leak will occur.
 *
 * Callers can validate that generation occurred without error in 2 ways:
 *
 *  -# Pass a non-NULL pointer to number_errors and verify that *number_errors
 *     is 0 after execution.
 *  -# Obtain the CXDiagnosticSet from the result and determine if that instance
 *     contains any errors.
 *
 * \param input The input instance to transform.
 * \param options Options to influence code generation.
 * \param action The type of code generation to perform.
 * \param number_errors [out] If non-null, will be set to the number of errors
 * that occurred during code generation.
 */
CLANGC_LINKAGE CGGenerationResult clang_codegen_generateOutput(CGInput input,
                                                           CGOptions options,
                                                            CGAction action,
                                                            int *number_errors);

/**
 * \brief Dispose of a code generation result instance.
 *
 * Once disposed, the instance is unusable.
 *
 * This must be called for every produced CGGenerationResult instance or a
 * memory leak will occur.
 *
 * \param result The instance to dispose.
 */
CLANGC_LINKAGE void clang_codegen_disposeResult(CGGenerationResult result);

/**
 * \brief Obtain a pointer to the result of the output generation.
 *
 * The data referenced by the pointer refers to memory owned by the
 * CGGenerationResult instance. If the caller wants the output to live longer
 * than the result instance, she can simply memcpy() the data to a buffer under
 * her control.
 *
 * It makes no sense to obtain the buffer without knowing the size, so if
 * \p size is NULL, the returned value will be NULL. The returned value can
 * also be NULL if an error occurred or if no output was generated.
 *
 * \param result The result instance to obtain data from.
 * \param size [out] Receives the size of the buffer being referred to.
 * \return Pointer to memory holding result of code generation.
 */
CLANGC_LINKAGE void * clang_codegen_getResultData(CGGenerationResult result,
                                                              size_t *size);

/**
 * \brief Obtain the diagnostics associated with a code generation result.
 *
 * This is called to view warnings and errors that occurred during code
 * generation.
 *
 * The obtained object is owned by the caller and it is the caller's
 * responsibility to dispose of the instance by calling
 * clang_disposeDiagnosticSet().
 *
 * The returned object has a lifetime not tied to that of the CGGenerationResult
 * instance.
 *
 * \param result Code generation result instance to obtain diagnostics from.
 */
CLANGC_LINKAGE CXDiagnosticSet clang_codegen_getResultDiagnosticSet(
                                                     CGGenerationResult result);

/**
 * @}
 */

#ifdef __cplusplus
}
#endif
#endif