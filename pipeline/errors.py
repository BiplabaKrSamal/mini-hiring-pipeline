"""Errors the API turns into JSON. Each message is written for the recruiter."""


class PipelineError(Exception):
    status = 400


class NotFound(PipelineError):
    status = 404


class Invalid(PipelineError):
    status = 422


class Conflict(PipelineError):
    status = 409
