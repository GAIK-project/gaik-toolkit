# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "opentelemetry-sdk>=1.30,<2",
#   "opentelemetry-exporter-otlp-proto-http>=1.30,<2",
# ]
# ///
"""Send one component run with one LLM call to the collector, the way an instrumented producer would.

Shows the producer side of the contract: OpenTelemetry only, OTLP/HTTP to the collector, standard
environment variables, OTel GenAI attribute names. The gaik.* names follow the draft event schema and
change with it (the schema is agreed jointly).

    uv run wp5-a1/examples/send_llm_call.py

Configuration (standard OpenTelemetry variables):
    OTEL_EXPORTER_OTLP_ENDPOINT   default http://127.0.0.1:4318
    OTEL_SERVICE_NAME             default example-producer
"""

import os
import time

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
os.environ.setdefault("OTEL_SERVICE_NAME", "example-producer")

provider = TracerProvider(resource=Resource.create())
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("gaik.example")

# A component run is the parent span; each model call is a child span.
with tracer.start_as_current_span("DataExtractor.run") as run:
    run.set_attribute("gaik.component", "DataExtractor")
    run.set_attribute("gaik.run.id", "example-run-1")
    run.set_attribute("gaik.config.blueprint_version", 1)
    # The identity is sent raw and pseudonymised by the collector; no destination stores it.
    run.set_attribute("enduser.id", "someone@example.com")

    with tracer.start_as_current_span("chat example-model", kind=trace.SpanKind.CLIENT) as call:
        call.set_attribute("gaik.event.class", "llm_call")
        call.set_attribute("gaik.component", "DataExtractor")
        call.set_attribute("gen_ai.operation.name", "chat")
        call.set_attribute("gen_ai.system", "azure.ai.openai")
        call.set_attribute("gen_ai.request.model", "example-model")
        time.sleep(0.2)  # the model call
        call.set_attribute("gen_ai.usage.input_tokens", 2104)
        call.set_attribute("gen_ai.usage.output_tokens", 423)
        call.set_attribute("gaik.cost.eur", 0.0061)
        # Content is off by default at the producer. Even if sent, the collector drops it.
        call.set_attribute("gen_ai.input.messages", "example prompt, dropped by the collector")

provider.shutdown()
print(f"sent to {os.environ['OTEL_EXPORTER_OTLP_ENDPOINT']} as {os.environ['OTEL_SERVICE_NAME']}")
