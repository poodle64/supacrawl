# ruff: noqa: UP007 — Union used at runtime for dynamic type construction; X | Y creates types.UnionType which behaves differently
"""
Utility functions for registering MCP tools with proper function metadata.

This module provides Pythonic, industry-standard patterns for creating
tool wrappers that preserve function metadata without monkey patching.

Usage:
    >>> from .tool_registration import create_tool_wrapper
    >>> wrapper = create_tool_wrapper(func, api_client)
"""

import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from functools import update_wrapper
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin  # noqa: UP035

from pydantic import Field

logger = logging.getLogger(__name__)


def remove_parameters_from_signature(
    sig: inspect.Signature,
    *param_names: str,
) -> inspect.Signature:
    """
    Remove specified parameters from a function signature.

    Args:
        sig: The original function signature
        *param_names: Names of parameters to remove

    Returns:
        New signature with specified parameters removed
    """
    params = [param for param in sig.parameters.values() if param.name not in param_names]
    return sig.replace(parameters=params)


def resolve_signature_annotations(
    func: Callable[..., Any],
    sig: inspect.Signature,
    *,
    skip: tuple[str, ...] = (),
) -> inspect.Signature:
    """Resolve any stringised (PEP 563) annotations on a signature to live objects.

    Tool modules use ``from __future__ import annotations``, so
    ``inspect.signature`` returns each annotation as a *string*
    (e.g. ``"Annotated[bool, Field(...)]"``). The wrapper this module builds
    carries those strings into ``wrapper.__annotations__``; when the wrapper is
    later re-wrapped (e.g. by a per-server error-translation decorator using
    ``functools.wraps``), the strings have to be re-evaluated by Pydantic against
    whatever ``__globals__`` the outer function happens to have. If that
    namespace lacks ``Annotated``/``Field``, schema generation raises
    ``KeyError`` and tool registration fails.

    Resolving each annotation here, against the *original function's* module
    globals (the namespace the author actually wrote the annotations in), makes
    the wrapper carry concrete annotation objects that no longer depend on any
    downstream ``__globals__``. This also lets the per-parameter normalisation
    transforms below operate on real types rather than no-op on strings.

    Parameters in ``skip`` (typically injected dependencies removed from the
    public signature) are left untouched, so a ``TYPE_CHECKING``-only client
    annotation (e.g. ``api_client: PayappsClient``) never has to resolve.

    Args:
        func: The function the signature was derived from; its ``__globals__``
            is the resolution namespace.
        sig: The signature whose parameter annotations should be resolved.
        skip: Parameter names to leave unresolved (injected dependencies).

    Returns:
        A signature with string parameter annotations replaced by live objects.
        Annotations that are already objects, or that fail to resolve, are left
        as-is.
    """
    func_globals = getattr(func, "__globals__", {})
    resolved_params = []
    for param in sig.parameters.values():
        annotation = param.annotation
        if param.name in skip or not isinstance(annotation, str):
            resolved_params.append(param)
            continue
        try:
            resolved = eval(annotation, func_globals)  # noqa: S307 — author-controlled annotation, not user input
        except NameError, AttributeError, SyntaxError:
            # Leave unresolved (e.g. a forward ref to a name not importable at
            # runtime); downstream handling treats it as a passthrough.
            resolved_params.append(param)
            continue
        resolved_params.append(param.replace(annotation=resolved))
    return sig.replace(parameters=resolved_params)


def create_tool_wrapper(
    endpoint_func: Callable[..., Awaitable[Any]],
    api_client: Any,
    *,
    optional_deps: dict[str, Any] | None = None,
    remove_params: tuple[str, ...] | None = None,
) -> Callable[..., Awaitable[Any]]:
    """
    Create a tool wrapper function that injects dependencies and preserves metadata.

    Uses functools.update_wrapper() for proper metadata handling instead of
    manual attribute assignment (monkey patching).

    Args:
        endpoint_func: The original endpoint function to wrap
        api_client: API client instance to inject as first parameter
        optional_deps: Optional dict of additional dependencies to inject
                      (e.g., {'node_metadata_service': service_instance})
        remove_params: Optional tuple of parameter names to remove from signature

    Returns:
        Wrapped function with proper metadata preserved

    Examples:
        >>> # Basic usage (just api_client)
        >>> wrapper = create_tool_wrapper(func, api_client)

        >>> # With optional dependency
        >>> wrapper = create_tool_wrapper(
        ...     func,
        ...     api_client,
        ...     optional_deps={'node_metadata_service': metadata_service}
        ... )

        >>> # With custom parameters to remove
        >>> wrapper = create_tool_wrapper(
        ...     func,
        ...     api_client,
        ...     remove_params=('internal_param',)
        ... )
    """
    # Get original signature
    original_sig = inspect.signature(endpoint_func)

    # Determine which parameters to remove
    params_to_remove = ["api_client"]

    # Add optional dependencies to removal list if they exist in signature
    if optional_deps:
        for dep_name in optional_deps.keys():
            if dep_name in original_sig.parameters:
                params_to_remove.append(dep_name)

    # Add custom parameters to remove
    if remove_params:
        params_to_remove.extend(remove_params)

    # Resolve stringised (PEP 563) annotations to live objects before building
    # the wrapper. Tool modules use `from __future__ import annotations`, so the
    # signature's annotations arrive as strings; carrying those strings into the
    # wrapper makes schema generation depend on the wrapper's (or a re-wrapper's)
    # __globals__ at TypeAdapter-build time. Injected dependency params are
    # skipped because their annotation may be a TYPE_CHECKING-only import that
    # cannot resolve at runtime (and they are removed from the public signature
    # anyway). See resolve_signature_annotations for the full rationale.
    original_sig = resolve_signature_annotations(endpoint_func, original_sig, skip=tuple(params_to_remove))

    # Create new signature without dependency parameters
    new_sig = remove_parameters_from_signature(original_sig, *params_to_remove)

    # Extract annotations for remaining parameters and update signature
    # For UUID parameters, add JSON schema metadata to prevent truncation
    # For integer/list parameters, make annotations more permissive to allow string normalisation
    new_annotations: dict[str, Any] = {}
    new_params = []
    for param in new_sig.parameters.values():
        param_name = param.name
        param_annotation = param.annotation if param.annotation != inspect.Parameter.empty else None

        # Check if this looks like a UUID parameter
        is_uuid_param = (
            param_name.lower().endswith("_id")
            or param_name.lower().endswith("_uuid")
            or param_name.lower().endswith("_flow")
            or param_name.lower() in ["id", "uuid"]
            or param_name.lower().startswith("flow_")
        )

        if param_annotation is None:
            # No annotation - keep as is
            new_params.append(param)
        elif is_uuid_param:
            # If it's an ID parameter and expects a string, add JSON schema metadata
            # This tells FastMCP to treat it as a string, preventing JSON coercion
            # Note: We do NOT add UUID format/pattern since not all IDs are UUIDs
            # (e.g., n8n uses 16-char alphanumeric workflow IDs and integer execution IDs)
            base_type = None  # Start as None, only set to str if confirmed
            is_optional = False

            if hasattr(param_annotation, "__origin__") and param_annotation.__origin__ is Union:
                args = get_args(param_annotation)
                if type(None) in args:
                    is_optional = True
                    # Find the non-None type
                    for arg in args:
                        if arg is not type(None) and arg is str:
                            base_type = str
                            break
            elif param_annotation is str:
                base_type = str
                if param.default != inspect.Parameter.empty and param.default is None:
                    is_optional = True

            # Add JSON schema metadata to prevent number coercion
            # Only apply to confirmed string types (not int, float, etc.)
            if base_type is str:
                if is_optional:
                    string_annotation: Any = Annotated[
                        str | None,
                        Field(
                            json_schema_extra={
                                "type": "string",
                            }
                        ),
                    ]
                else:
                    string_annotation = Annotated[
                        str,
                        Field(
                            json_schema_extra={
                                "type": "string",
                            }
                        ),
                    ]
                new_annotations[param_name] = string_annotation
                new_params.append(param.replace(annotation=string_annotation))
                logger.debug(f"Added string schema to '{param_name}' to prevent coercion")
            else:
                new_annotations[param_name] = param_annotation
                new_params.append(param)
        else:
            # For integer parameters, make annotation accept both int and str
            # This allows FastMCP validation to pass, then wrapper normalises
            if param_annotation is int:
                new_annotations[param_name] = Union[int, str]
                new_params.append(param.replace(annotation=Union[int, str]))
            elif hasattr(param_annotation, "__origin__") and param_annotation.__origin__ is Union:
                args = get_args(param_annotation)
                # Check if Union contains int (for Optional[int])
                if int in args:
                    # Add str to Union to allow string normalisation
                    new_args = list(args)
                    if str not in new_args:
                        new_args.append(str)
                    combined = Union[tuple(new_args)]  # type: ignore[valid-type]
                    new_annotations[param_name] = combined
                    new_params.append(param.replace(annotation=combined))
                # Check if Union contains list (for Optional[List[...]])
                elif any(
                    hasattr(arg, "__origin__") and arg.__origin__ is list for arg in args if arg is not type(None)
                ):
                    # Find the list type in the Union
                    list_type = None
                    for arg in args:
                        if arg is not type(None) and hasattr(arg, "__origin__") and arg.__origin__ is list:
                            list_type = arg
                            break
                    if list_type:
                        # Create Union[List[...], str] to allow string normalisation
                        new_args = [arg for arg in args if arg is not type(None)]
                        new_args.append(str)
                        combined = Union[tuple(new_args)]  # type: ignore[valid-type]
                        new_annotations[param_name] = combined
                        new_params.append(param.replace(annotation=combined))
                    else:
                        new_annotations[param_name] = param_annotation
                        new_params.append(param)
                # Check if Union contains dict (for Optional[Dict[...]] or dict[...] | None)
                # This handles Python 3.10+ where types.UnionType is typing.Union
                elif any(
                    arg is dict or (hasattr(arg, "__origin__") and arg.__origin__ is dict)
                    for arg in args
                    if arg is not type(None)
                ):
                    # Add str to Union to allow string normalisation
                    new_args = list(args)
                    if str not in new_args:
                        new_args.append(str)
                    combined = Union[tuple(new_args)]  # type: ignore[valid-type]
                    new_annotations[param_name] = combined
                    new_params.append(param.replace(annotation=combined))
                else:
                    new_annotations[param_name] = param_annotation
                    new_params.append(param)
            # For list parameters, make annotation accept both list and str
            elif param_annotation is list:
                new_annotations[param_name] = Union[list, str]
                new_params.append(param.replace(annotation=Union[list, str]))
            elif hasattr(param_annotation, "__origin__") and param_annotation.__origin__ is list:
                # Create Union[list[...], str] to allow string normalisation
                combined = Union[param_annotation, str]
                new_annotations[param_name] = combined
                new_params.append(param.replace(annotation=combined))
            # For dict parameters, make annotation accept both dict and str
            elif param_annotation is dict:
                new_annotations[param_name] = Union[dict, str]
                new_params.append(param.replace(annotation=Union[dict, str]))
            elif hasattr(param_annotation, "__origin__") and param_annotation.__origin__ is dict:
                # Create Union[dict[...], str] to allow string normalisation
                combined = Union[param_annotation, str]
                new_annotations[param_name] = combined
                new_params.append(param.replace(annotation=combined))
            # For Dict[...] from typing
            elif hasattr(param_annotation, "__origin__") and param_annotation.__origin__ is type(dict):
                # Handle Dict[K, V] from typing
                combined = Union[param_annotation, str]
                new_annotations[param_name] = combined
                new_params.append(param.replace(annotation=combined))
            # Handle Python 3.10+ union syntax (e.g., dict[str, Any] | None)
            elif isinstance(param_annotation, UnionType):
                args = get_args(param_annotation)
                # Check if any arg in the union is a dict type
                has_dict = False
                for arg in args:
                    if arg is dict:
                        has_dict = True
                        break
                    if get_origin(arg) is dict:
                        has_dict = True
                        break
                if has_dict:
                    # Add str to the union to allow string normalisation
                    combined = Union[param_annotation, str]
                    new_annotations[param_name] = combined
                    new_params.append(param.replace(annotation=combined))
                else:
                    new_annotations[param_name] = param_annotation
                    new_params.append(param)
            else:
                new_annotations[param_name] = param_annotation
                new_params.append(param)

    # Update signature with modified parameters
    new_sig = new_sig.replace(parameters=new_params)

    # Add return type annotation if present
    if original_sig.return_annotation != inspect.Signature.empty:
        new_annotations["return"] = original_sig.return_annotation

    # Determine call order: api_client first, then optional deps in signature order
    dep_values = [api_client]

    if optional_deps:
        # Add optional deps in the order they appear in the original signature
        for param_name in original_sig.parameters.keys():
            if param_name in optional_deps and param_name != "api_client":
                dep_values.append(optional_deps[param_name])

    # Create wrapper function with UUID parameter protection
    # FastMCP may coerce UUIDs starting with digits to integers, truncating them
    # We need to convert them back to strings before passing to the function
    def _normalize_params(
        kwargs: dict[str, Any],
        sig: inspect.Signature,
        orig_sig: inspect.Signature,
    ) -> dict[str, Any]:
        """
        Normalise parameter types for tool functions.

        This function performs simple type normalisation:
        1. Converts string "null" to None for Optional parameters
        2. Converts non-string values to strings for string parameters
        3. Converts string numbers to integers for integer parameters
        4. Parses JSON strings to lists/dicts for complex parameters

        All semantic validation (UUID format, length, etc.) happens in validate_id.
        """
        normalised_kwargs = kwargs.copy()

        # Iterate over original signature parameters (skip api_client and dependencies)
        skip_params = {"api_client"}
        if optional_deps:
            skip_params.update(optional_deps.keys())

        for param_name, param in orig_sig.parameters.items():
            # Skip api_client and optional dependencies (they're injected, not passed via kwargs)
            if param_name in skip_params:
                continue

            # Only process if parameter is in kwargs
            if param_name not in normalised_kwargs:
                continue

            value = normalised_kwargs[param_name]

            # Skip if already None
            if value is None:
                continue

            param_annotation = param.annotation

            # Check if parameter is Optional (can accept None)
            is_optional = False

            # Check default value - if default is None, parameter is optional
            if param.default != inspect.Parameter.empty and param.default is None:
                is_optional = True

            # Check type annotation for Optional/Union with None
            if param_annotation != inspect.Parameter.empty and hasattr(param_annotation, "__origin__"):
                if param_annotation.__origin__ is Union:
                    args = get_args(param_annotation)
                    if type(None) in args:
                        is_optional = True

            # Normalise "null" string to None for Optional parameters
            # This handles cases where JSON "null" string is passed instead of actual None
            if isinstance(value, str) and value.lower() == "null":
                if is_optional:
                    logger.debug(f"Normalising string 'null' to None for optional parameter {param_name}")
                    normalised_kwargs[param_name] = None
                    continue
                else:
                    logger.warning(
                        f"Received 'null' string for non-optional parameter {param_name} "
                        f"(annotation={param_annotation!r}, default={param.default!r})"
                    )

            # Handle integer parameters - convert string numbers to int
            expects_integer = False
            if param_annotation != inspect.Parameter.empty:
                if param_annotation is int:
                    expects_integer = True
                elif hasattr(param_annotation, "__origin__") and param_annotation.__origin__ is Union:
                    args = get_args(param_annotation)
                    if int in args:
                        expects_integer = True

            if expects_integer and not isinstance(value, int):
                if isinstance(value, str):
                    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
                        logger.debug(f"Normalising '{value}' to int for param {param_name}")
                        normalised_kwargs[param_name] = int(value)
                    else:
                        logger.warning(f"Cannot convert '{value}' to int for param {param_name}")
                elif isinstance(value, (float, bool)):
                    logger.debug(f"Normalising {type(value).__name__} to int for {param_name}")
                    normalised_kwargs[param_name] = int(value)

            # Handle list parameters - convert string representations to lists
            expects_list = False
            list_item_type = None
            if param_annotation != inspect.Parameter.empty:
                # Check if annotation is list or List[...]
                if param_annotation is list:
                    expects_list = True
                elif hasattr(param_annotation, "__origin__"):
                    if param_annotation.__origin__ is list:
                        expects_list = True
                        args = get_args(param_annotation)
                        if args:
                            list_item_type = args[0]
                    elif param_annotation.__origin__ is Union:
                        args = get_args(param_annotation)
                        for arg in args:
                            if arg is list:
                                expects_list = True
                                break
                            elif hasattr(arg, "__origin__") and arg.__origin__ is list:
                                expects_list = True
                                list_args = get_args(arg)
                                if list_args:
                                    list_item_type = list_args[0]
                                break

            if expects_list and not isinstance(value, list):
                if isinstance(value, str):
                    # Try to parse as JSON array
                    try:
                        parsed = json.loads(value)
                        if isinstance(parsed, list):
                            logger.debug(f"Normalising string '{value}' to list for parameter {param_name}")
                            # Convert list items to appropriate type if specified
                            if list_item_type is int:
                                normalised_list = []
                                for item in parsed:
                                    if isinstance(item, str) and item.isdigit():
                                        normalised_list.append(int(item))
                                    elif isinstance(item, int):
                                        normalised_list.append(item)
                                    else:
                                        normalised_list.append(item)
                                normalised_kwargs[param_name] = normalised_list
                            else:
                                normalised_kwargs[param_name] = parsed
                        else:
                            logger.warning(f"JSON '{value}' not a list for {param_name}")
                    except json.JSONDecodeError, ValueError:
                        logger.warning(f"Cannot parse string '{value}' as JSON list for parameter {param_name}")
                elif isinstance(value, (tuple, set)):
                    logger.debug(f"Normalising {type(value).__name__} to list for parameter {param_name}")
                    normalised_kwargs[param_name] = list(value)
                    continue

            # Handle dict parameters - convert string representations to dicts
            expects_dict = False
            if param_annotation != inspect.Parameter.empty:
                # Check if annotation is dict or Dict[...]
                if param_annotation is dict:
                    expects_dict = True
                elif hasattr(param_annotation, "__origin__"):
                    if param_annotation.__origin__ is dict:
                        expects_dict = True
                    elif param_annotation.__origin__ is Union:
                        args = get_args(param_annotation)
                        for arg in args:
                            if arg is dict:
                                expects_dict = True
                                break
                            elif hasattr(arg, "__origin__") and arg.__origin__ is dict:
                                expects_dict = True
                                break
                # Handle Python 3.10+ union syntax (e.g., dict[str, Any] | None)
                elif isinstance(param_annotation, UnionType):
                    args = get_args(param_annotation)
                    for arg in args:
                        if arg is dict:
                            expects_dict = True
                            break
                        if get_origin(arg) is dict:
                            expects_dict = True
                            break

            if expects_dict and not isinstance(value, dict):
                if isinstance(value, str):
                    try:
                        parsed_dict = json.loads(value)
                        if isinstance(parsed_dict, dict):
                            logger.debug(f"Normalising to dict for {param_name}")
                            normalised_kwargs[param_name] = parsed_dict
                            continue
                        else:
                            logger.warning(f"JSON not dict for {param_name}")
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON for dict param {param_name}")

            # Convert non-string values to strings for string parameters
            expects_string = False
            if param_annotation != inspect.Parameter.empty:
                if param_annotation is str:
                    expects_string = True
                elif hasattr(param_annotation, "__origin__") and param_annotation.__origin__ is Union:
                    args = get_args(param_annotation)
                    if str in args:
                        expects_string = True

            if expects_string and not isinstance(value, str):
                logger.debug(f"Normalising {type(value).__name__} to str for {param_name}")
                normalised_kwargs[param_name] = str(value)

        return normalised_kwargs

    if len(dep_values) > 1:
        # Multiple dependencies: pass as positional args in correct order
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Normalise parameters before calling the function
            normalised_kwargs = _normalize_params(kwargs, new_sig, original_sig)
            return await endpoint_func(*dep_values, *args, **normalised_kwargs)
    else:
        # Simple case: just api_client
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Normalise parameters before calling the function
            normalised_kwargs = _normalize_params(kwargs, new_sig, original_sig)
            return await endpoint_func(api_client, *args, **normalised_kwargs)

    # Initialise __doc__ to avoid None issues with update_wrapper
    wrapper.__doc__ = endpoint_func.__doc__ or f"{endpoint_func.__name__} endpoint"

    # Use functools.update_wrapper() for proper metadata handling
    # This handles __name__, __module__, __qualname__
    # Note: We handle __doc__ and __annotations__ separately
    update_wrapper(
        wrapper,
        endpoint_func,
        assigned=("__name__", "__module__", "__qualname__"),
    )

    # Set signature and annotations (these aren't handled by update_wrapper)
    # CRITICAL: Set signature BEFORE FastMCP inspects the function
    wrapper.__signature__ = new_sig  # type: ignore[attr-defined]
    _set_authoritative_annotations(wrapper, new_annotations)

    return wrapper


def _set_authoritative_annotations(func: Callable[..., Any], annotations: dict[str, Any]) -> None:
    """Make ``annotations`` the authoritative annotation source for ``func``.

    On Python 3.14 (PEP 749) a function's ``__annotations__`` is computed lazily
    from ``__annotate__`` when one is present. Assigning ``__annotations__`` is
    not enough on its own once any later step copies an ``__annotate__`` over the
    top, so the stored ``__annotate__`` is cleared here. With ``__annotate__``
    cleared, ``__annotations__`` is the single source of truth that Pydantic's
    ``get_function_type_hints`` reads when building the tool schema.
    """
    func.__annotations__ = annotations
    # PEP 749: drop any annotate callable so the explicit dict above wins.
    if getattr(func, "__annotate__", None) is not None:
        func.__annotate__ = None  # type: ignore[attr-defined]


def preserve_tool_metadata(
    wrapper: Callable[..., Any],
    wrapped: Callable[..., Any],
) -> None:
    """Copy the FastMCP-introspected metadata from ``wrapped`` onto ``wrapper``.

    A per-server decorator that re-wraps a ``create_tool_wrapper`` result (e.g. an
    error-translation layer) must carry forward the metadata FastMCP and Pydantic
    read to build the tool schema: the ``__signature__`` (which lists the tool's
    parameters) and the ``__annotations__`` (which give each parameter its type).

    ``functools.wraps`` is not sufficient for either:

    - ``__signature__`` was never in ``WRAPPER_ASSIGNMENTS``.
    - ``__annotations__`` was in ``WRAPPER_ASSIGNMENTS`` up to Python 3.13, but
      Python 3.14 (PEP 749) replaced it with ``__annotate__``. A bare
      ``*args/**kwargs`` re-wrapper has an empty ``__annotate__``, so ``wraps``
      now leaves the re-wrapper with no parameter annotations while its copied
      ``__signature__`` still lists the parameters. Pydantic then raises
      ``KeyError: '<param>'`` (signature lists the param, type-hints do not).

    Call this AFTER ``functools.wraps`` has run on ``wrapper``. The annotations
    are resolved to live objects by ``create_tool_wrapper``, so they no longer
    depend on the re-wrapper's own ``__globals__`` to evaluate.
    """
    signature = getattr(wrapped, "__signature__", None)
    if signature is not None:
        wrapper.__signature__ = signature  # type: ignore[attr-defined]
    _set_authoritative_annotations(wrapper, dict(getattr(wrapped, "__annotations__", {})))
