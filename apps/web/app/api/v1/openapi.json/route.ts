import spec from "@/openapi.json";

/** The API's contract (OpenAPI 3.1), public: generate a client from it or read it in a viewer. */
export function GET() {
  return Response.json(spec);
}
