"""El Cónclave pasa de 3 voces a 5 ROLES × 5 linajes (2026-08-01).

El operador trajo dos repos (`aiwithremy/claude-skills-llm-council`,
`gcpdev/llm-council-skill`). El primero reveló el hallazgo que reordena el
diseño: sus 5 voces no son 5 MODELOS distintos, son 5 ROLES de pensamiento
(Contrarian, First Principles, Expansionist, Outsider, Executor) con una
ronda de revisión anónima entre pares. Nuestro eje histórico es el LINAJE de
preentrenamiento (US/CN/EU). Son ejes ORTOGONALES: un rol por linaje cubre
ambos a la vez.

Y explica la patología medida el 31-jul: `_HOSTILE_PROMPT` ES el Contrarian
aplicado a los tres asientos — corríamos un panel de tres Contrarians. Por
eso Gemini calificó BLOCKING un cambio de timeout de 30s a 60s: no es una
rareza del modelo, es que el panel entero sólo sabía jugar un papel.
"""

from __future__ import annotations

from atlas.core.deliberation_council import (
    COUNCIL_ROLES,
    build_council_reviewers,
)
from atlas.core.inference_hub import DEFAULT_PROVIDERS


class TestFiveDistinctRoles:
    def test_there_are_exactly_five_roles(self) -> None:
        assert len(COUNCIL_ROLES) == 5

    def test_the_contrarian_prompt_is_untouched(self) -> None:
        """El operador fue explícito: 'el Cónclave estuvo bien hasta ahora'.
        No se ablanda el prompt hostil — se le añaden los otros cuatro."""
        from atlas.core.deliberation_council import _HOSTILE_PROMPT

        contrarian = next(s for s in COUNCIL_ROLES if s.role == "contrarian")
        assert contrarian.prompt == _HOSTILE_PROMPT

    def test_the_four_new_roles_have_distinct_prompts(self) -> None:
        prompts = {s.prompt for s in COUNCIL_ROLES}
        assert len(prompts) == 5, "dos roles no deben compartir el mismo prompt"

    def test_every_role_prompt_still_demands_a_severity_first_line(self) -> None:
        """Todos los roles, no sólo el Contrarian, deben mantener el formato
        que `LlmReviewer.review()` sabe parsear: severidad en la 1ª línea."""
        for seat in COUNCIL_ROLES:
            assert "NONE MINOR MAJOR BLOCKING" in seat.prompt, seat.role

    def test_each_role_sits_on_a_distinct_lineage(self) -> None:
        """Cada rol cubre un linaje distinto -- el hallazgo de esta sesión es
        que ambos ejes (rol y linaje) son ortogonales y deben cubrirse juntos,
        no que uno sustituya al otro."""
        primaries = [seat.lineage[0] for seat in COUNCIL_ROLES]
        assert len(set(primaries)) == 5


class TestBuildCouncilReviewers:
    def test_builds_one_reviewer_per_seat_whose_lineage_is_alive(self) -> None:
        """Antes era `== 5` a secas. Eso ataba el test al estado de los
        proveedores en vez de al contrato: en cuanto `nvidia_glm` se degradó
        (2026-08-05, DOWN tras días de smoke muerto) el test fallaba sin que
        nada del Cónclave estuviera roto. Lo que se prueba ahora es la regla —
        se monta un asiento por cada papel cuyo linaje tenga algún proveedor
        NO caído, ni uno más."""
        from atlas.core.inference_hub import DEFAULT_PROVIDERS, ProviderStatus

        alive = {p.name for p in DEFAULT_PROVIDERS if p.status is not ProviderStatus.DOWN}
        expected = sum(1 for seat in COUNCIL_ROLES if set(seat.lineage) & alive)

        reviewers = build_council_reviewers()

        assert len(reviewers) == expected
        assert 0 < expected <= len(COUNCIL_ROLES)

    def test_covers_one_distinct_lineage_per_built_seat(self) -> None:
        """El diseño DECLARA 5 asientos, uno por linaje. Cuántos se
        CONSTRUYEN depende de qué proveedores estén vivos: desde el
        2026-08-05 `nvidia_glm` (único Zhipu) está DOWN tras días de smoke
        muerto, así que salen 4. Lo que no puede romperse es la ortogonalidad
        — un proveedor por asiento, sin repetir linaje."""
        reviewers = build_council_reviewers()
        provs = {r.provider for r in reviewers}
        assert len(provs) == len(reviewers), "dos asientos comparten proveedor"
        assert len(COUNCIL_ROLES) == 5, "el diseño sigue declarando 5 papeles"

    def test_reviewer_id_carries_the_role_not_just_the_provider(self) -> None:
        """Antes `reviewer_id` era sólo el nombre del proveedor -- con 5
        roles hace falta poder distinguir en logs/síntesis QUÉ papel objetó,
        no sólo qué proveedor respondió."""
        reviewers = build_council_reviewers()
        ids = {r.reviewer_id for r in reviewers}
        assert any("contrarian" in rid for rid in ids)

    def test_zhipu_and_alibaba_are_no_longer_the_same_seat(self) -> None:
        """Defecto encontrado al diseñar: el viejo _TRIO_LINEAGE_FALLBACKS
        ponía a Qwen (Alibaba) de primario y GLM (Zhipu) de fallback en el
        MISMO asiento "CN" -- dos laboratorios distintos cruzados dentro de
        un único slot, justo lo que la regla de "nunca cruzar de linaje" en
        el comentario contiguo prohibía. Con 5 roles cada uno tiene su
        propio asiento."""
        zhipu = next(s for s in COUNCIL_ROLES if s.role == "expansionist")
        alibaba = next(s for s in COUNCIL_ROLES if s.role == "executor")
        # Se comprueba sobre la TABLA de asientos, no sobre los construidos:
        # `nvidia_glm` está DOWN desde el 2026-08-05 y su asiento no se monta,
        # pero la separación de linajes que este test defiende es del DISEÑO y
        # sigue viva — mirar los construidos haría que el test dejara de
        # probar su propia tesis en cuanto un proveedor se cae.
        assert "nvidia_glm" in zhipu.lineage
        assert "groq_qwen3" in alibaba.lineage
        assert not set(zhipu.lineage) & set(alibaba.lineage)

    def test_a_missing_lineage_leaves_that_seat_empty_not_fabricated(self) -> None:
        """Mismo contrato que build_trio_reviewers: sin proveedor del linaje
        en el pool, el asiento queda vacío -- nunca se inventa un sustituto
        de otro linaje (rompería la ortogonalidad rol×linaje)."""
        pool = [p for p in DEFAULT_PROVIDERS if p.name not in {"groq_qwen3", "ollama_local"}]
        reviewers = build_council_reviewers(providers=pool)
        provs = {r.provider for r in reviewers}
        assert "groq_qwen3" not in provs      # el asiento Alibaba desaparece
        assert "groq_llama_70b" in provs      # los demás no se tocan
        assert not any(r.reviewer_id.startswith("executor:") for r in reviewers)


class TestBackwardCompatibleAlias:
    def test_build_trio_reviewers_is_now_the_five_seat_council(self) -> None:
        """Todos los callers existentes (orchestrator, atlas_coder, code_cycle,
        3 scripts) llaman a `build_trio_reviewers()` -- se convierte en alias
        del constructor de 5 asientos para que hereden las 5 voces sin tocar
        cada call-site uno a uno."""
        from atlas.core.deliberation_council import build_trio_reviewers

        assert build_trio_reviewers is build_council_reviewers
