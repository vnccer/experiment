from copy import deepcopy

from pydantic import ValidationError

from agentdojo.functions_runtime import FunctionsRuntime

from .checker import ActionDeniedError, authorize


class CampusRuntime(FunctionsRuntime):
    """Strict, audited execution boundary. No parameter coercion or nested calls."""

    def run_function(self, env, function, kwargs, raise_on_error=False):
        state = env.sandbox
        record = {"sequence": len(state.proposed_actions) + 1, "action": function, "args": deepcopy(dict(kwargs))}
        state.proposed_actions.append(record)
        try:
            if function not in self.functions:
                raise ActionDeniedError("unknown_tool")
            schema = self.functions[function].parameters
            if set(kwargs) != set(schema.model_fields):
                raise ActionDeniedError("missing_or_extra_parameters")
            try:
                args = schema.model_validate(kwargs, strict=True).model_dump()
            except ValidationError as exc:
                raise ActionDeniedError("invalid_parameter_types_or_values") from exc
            authorize(state, function, args)
        except ActionDeniedError as exc:
            state.rejected_actions.append(record | {"reason": str(exc)})
            if raise_on_error:
                raise
            return "", f"ActionDeniedError: {exc}"
        result, error = super().run_function(env, function, args)
        if error:
            # Execution failures are distinct from authorization rejection.
            if raise_on_error:
                raise RuntimeError(error)
        else:
            state.executed_actions.append(deepcopy(record))
        return result, error
