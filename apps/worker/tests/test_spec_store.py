"""Run 7, M3: specs in Postgres with pgvector, against the test database (FakeEmbedder)."""

from worker.db.models import Spec, SpecChunk, Target, Workspace
from worker.db.tenant import enter_tenant
from worker.spec_store import SpecRetriever, nearest, origin_of, sync_target, target_for
from worker.specs import FakeEmbedder

BOOKING = """# Booking
## Stay summary
- The total is the price per night times the number of nights.
## Guest details
- The guest's email address must be a valid address.
"""
LOGIN = """# Sign in
- A wrong password shows an error next to the password field.
"""


def make_target(session, workspace_id, origin="http://shop.test"):
    target = Target(workspace_id=workspace_id, origin=origin)
    session.add(target)
    session.flush()
    return target


def add_spec(session, target, title, body):
    spec = Spec(workspace_id=target.workspace_id, target_id=target.id, title=title, body=body)
    session.add(spec)
    session.commit()
    return spec


def test_a_runs_target_is_found_by_its_origin(sessions, workspace):
    with sessions() as session:
        target = make_target(session, workspace.id)
        session.commit()
        assert origin_of("http://shop.test/cart?x=1") == "http://shop.test"
        assert target_for(session, workspace.id, "http://shop.test/products/2").id == target.id
        assert target_for(session, workspace.id, "http://other.test/") is None


def test_sync_chunks_and_embeds_pending_specs_once(sessions, workspace):
    embedder = FakeEmbedder()
    with sessions() as session:
        target = make_target(session, workspace.id)
        add_spec(session, target, "Booking", BOOKING)
        assert sync_target(session, target.id, embedder) == 2
        assert sync_target(session, target.id, embedder) == 0  # nothing changed
        chunks = session.query(SpecChunk).order_by(SpecChunk.ord).all()
        assert [c.heading for c in chunks] == ["Booking > Stay summary", "Booking > Guest details"]
        assert len(chunks[0].embedding) == 768


def test_an_edited_spec_is_chunked_again_and_its_old_chunks_go(sessions, workspace):
    embedder = FakeEmbedder()
    with sessions() as session:
        target = make_target(session, workspace.id)
        spec = add_spec(session, target, "Booking", BOOKING)
        sync_target(session, target.id, embedder)
        spec.body = LOGIN
        session.commit()
        assert sync_target(session, target.id, embedder) == 1
        assert [c.heading for c in session.query(SpecChunk)] == ["Sign in"]


def test_another_embedding_model_means_embedding_again(sessions, workspace):
    with sessions() as session:
        target = make_target(session, workspace.id)
        add_spec(session, target, "Booking", BOOKING)
        sync_target(session, target.id, FakeEmbedder())
        other = FakeEmbedder()
        other.model = "another-model"
        assert sync_target(session, target.id, other) == 2


def test_nearest_returns_the_closest_chunks_first(sessions, workspace):
    embedder = FakeEmbedder()
    with sessions() as session:
        target = make_target(session, workspace.id)
        add_spec(session, target, "Booking", BOOKING)
        add_spec(session, target, "Login", LOGIN)
        sync_target(session, target.id, embedder)
        [query] = embedder.embed(["wrong password error next to the password field"], "query")
        found = nearest(session, target.id, query)
        assert found[0].heading == "Sign in"
        assert found[0].distance <= found[-1].distance


def test_the_retriever_labels_and_caches_per_page(sessions, workspace):
    calls = []

    class CountingEmbedder(FakeEmbedder):
        def embed(self, texts, kind):
            calls.append(kind)
            return super().embed(texts, kind)

    embedder = CountingEmbedder()
    with sessions() as session:
        target = make_target(session, workspace.id)
        add_spec(session, target, "Booking", BOOKING)
        sync_target(session, target.id, embedder)
        calls.clear()
        retriever = SpecRetriever(session, target.id, embedder, max_distance=2.0)
        first = retriever.for_page("http://shop.test/rooms/1", "Room", "total price per night")
        again = retriever.for_page("http://shop.test/rooms/1", "Room", "total price per night")
        assert calls == ["query"]  # the second visit is served from the cache
        assert [c.label for c in first] == [c.label for c in again] == ["S1", "S2"]
        assert first[0].heading == "Booking > Stay summary"


def test_a_retrieval_failure_means_no_requirements_not_a_failed_run(sessions, workspace):
    class Down(FakeEmbedder):
        def embed(self, texts, kind):
            raise ConnectionError("ollama is not running")

    with sessions() as session:
        target = make_target(session, workspace.id)
        session.commit()
        assert SpecRetriever(session, target.id, Down()).for_page("http://shop.test/", "", "") == []


def test_a_tenant_never_sees_another_workspaces_specs(sessions, worker_sessions, workspace):
    embedder = FakeEmbedder()
    with sessions() as session:
        other = Workspace(name="Other", slug="other")
        session.add(other)
        session.flush()
        mine, theirs = make_target(session, workspace.id), make_target(session, other.id)
        add_spec(session, mine, "Booking", BOOKING)
        add_spec(session, theirs, "Login", LOGIN)
        sync_target(session, mine.id, embedder)
        sync_target(session, theirs.id, embedder)
        mine_id, theirs_id = mine.id, theirs.id
    with worker_sessions() as session:
        enter_tenant(session, workspace.id)
        assert {s.title for s in session.query(Spec)} == {"Booking"}
        assert session.query(SpecChunk).filter_by(target_id=theirs_id).count() == 0
        [query] = embedder.embed(["password"], "query")
        assert all(c.spec_title == "Booking" for c in nearest(session, mine_id, query))
        assert nearest(session, theirs_id, query) == []
