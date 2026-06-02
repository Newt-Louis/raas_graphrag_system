--
-- PostgreSQL database dump
--

\restrict kf1SnxyWp6HhMRbv156pEDpK0CiMAkOycRogH80ySsbgrhudaImLdmOXlAkp8cP

-- Dumped from database version 17.10
-- Dumped by pg_dump version 17.10

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: llm_model_profiles; Type: TABLE; Schema: public; Owner: graphrag_user
--

CREATE TABLE public.llm_model_profiles (
    id uuid NOT NULL,
    provider_id uuid NOT NULL,
    api_key_id uuid NOT NULL,
    model_id uuid,
    profile_name character varying(255) NOT NULL,
    model_name character varying(255) NOT NULL,
    api_base text,
    endpoint_id character varying(120),
    temperature double precision,
    top_p double precision,
    top_k integer,
    max_output_tokens integer,
    timeout_seconds integer DEFAULT 120 NOT NULL,
    cost_per_1k_input_tokens numeric(12,8),
    cost_per_1k_output_tokens numeric(12,8),
    extra_parameters jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.llm_model_profiles OWNER TO graphrag_user;

--
-- Name: llm_rotation_pools; Type: TABLE; Schema: public; Owner: graphrag_user
--

CREATE TABLE public.llm_rotation_pools (
    id uuid NOT NULL,
    tenant_id uuid,
    app_id uuid,
    name character varying(120) NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    is_enabled boolean DEFAULT true NOT NULL,
    current_position integer DEFAULT 0 NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    profile_id uuid NOT NULL,
    rotation_order integer DEFAULT 0 NOT NULL,
    weight integer DEFAULT 1 NOT NULL,
    is_locked boolean DEFAULT false NOT NULL,
    lock_reason text,
    today_quota_exhausted boolean DEFAULT false NOT NULL,
    quota_exhausted_until timestamp with time zone,
    rate_limited_until timestamp with time zone,
    last_used_at timestamp with time zone,
    daily_request_count integer DEFAULT 0 NOT NULL,
    minute_request_count integer DEFAULT 0 NOT NULL,
    success_count integer DEFAULT 0 NOT NULL,
    failure_count integer DEFAULT 0 NOT NULL
);


ALTER TABLE public.llm_rotation_pools OWNER TO graphrag_user;

--
-- Data for Name: llm_model_profiles; Type: TABLE DATA; Schema: public; Owner: graphrag_user
--

COPY public.llm_model_profiles (id, provider_id, api_key_id, model_id, profile_name, model_name, api_base, endpoint_id, temperature, top_p, top_k, max_output_tokens, timeout_seconds, cost_per_1k_input_tokens, cost_per_1k_output_tokens, extra_parameters, created_at, updated_at) FROM stdin;
0ff49be4-3dbe-4ca9-a70f-3a26b5f0e64e	23be80c6-43c2-4ebf-8c6e-517cd165c63c	a5f49ac5-b2f2-4bf7-8b31-b20df8119016	\N	Gemini 2.5 Flash	gemini-2.5-flash	\N	\N	0.3	0.9	\N	32967	120	\N	\N	{}	2026-06-01 06:48:12.495873+00	2026-06-01 06:48:12.495873+00
38c313f3-d383-4e5c-a0c8-31d17721bb24	23be80c6-43c2-4ebf-8c6e-517cd165c63c	a5f49ac5-b2f2-4bf7-8b31-b20df8119016	\N	Gemini 2.5 Flash Lite	gemini-2.5-flash-lite	\N	\N	0.3	0.9	\N	32967	120	\N	\N	{}	2026-06-01 06:53:08.118755+00	2026-06-01 06:53:08.118755+00
8353d573-3dc6-4816-ad34-f56677dbdcf3	23be80c6-43c2-4ebf-8c6e-517cd165c63c	a5f49ac5-b2f2-4bf7-8b31-b20df8119016	\N	Gemini 3 Flash Preview	gemini-3-flash-preview	\N	\N	0.3	0.9	\N	32967	120	\N	\N	{}	2026-06-01 06:55:06.701171+00	2026-06-01 06:55:06.701171+00
93792f40-341a-4de7-a4d8-856be4573d8f	23be80c6-43c2-4ebf-8c6e-517cd165c63c	a5f49ac5-b2f2-4bf7-8b31-b20df8119016	\N	Gemma 4 31b	gemma-4-31b-it	\N	\N	0.3	0.9	\N	32967	120	\N	\N	{}	2026-06-01 07:03:49.814732+00	2026-06-01 07:03:49.814732+00
f4ac047f-6c03-44d7-9664-5ac2aba275ee	23be80c6-43c2-4ebf-8c6e-517cd165c63c	a5f49ac5-b2f2-4bf7-8b31-b20df8119016	\N	Gemma 4 26b	gemma-4-26b-a4b-it	\N	\N	0.3	0.9	\N	32967	120	\N	\N	{}	2026-06-01 07:04:35.408646+00	2026-06-01 07:04:35.408646+00
77c8d4b5-8dce-495c-9218-5ad7e49da687	23be80c6-43c2-4ebf-8c6e-517cd165c63c	a5f49ac5-b2f2-4bf7-8b31-b20df8119016	\N	Gemini 3.5 Flash	gemini-3.5-flash	\N	\N	0.3	0.9	\N	32967	120	\N	\N	{}	2026-06-01 08:36:31.887602+00	2026-06-01 08:36:31.887602+00
e7f1361e-14f7-4af9-bcf9-2a51d908e5c2	23be80c6-43c2-4ebf-8c6e-517cd165c63c	a5f49ac5-b2f2-4bf7-8b31-b20df8119016	\N	Gemini 3.1 Flash Lite	gemini-3.1-flash-lite	\N	\N	0.3	0.8	\N	32967	120	\N	\N	{}	2026-05-27 04:40:47.724264+00	2026-06-01 08:50:10.025459+00
\.


--
-- Data for Name: llm_rotation_pools; Type: TABLE DATA; Schema: public; Owner: graphrag_user
--

COPY public.llm_rotation_pools (id, tenant_id, app_id, name, is_default, is_enabled, current_position, description, created_at, updated_at, profile_id, rotation_order, weight, is_locked, lock_reason, today_quota_exhausted, quota_exhausted_until, rate_limited_until, last_used_at, daily_request_count, minute_request_count, success_count, failure_count) FROM stdin;
e7f1361e-14f7-4af9-bcf9-2a51d908e5c2	\N	\N	Gemini 3.1 Flash Lite	f	t	0	\N	2026-05-27 04:40:47.724264+00	2026-05-27 04:40:47.724264+00	e7f1361e-14f7-4af9-bcf9-2a51d908e5c2	1	1	f	\N	f	\N	\N	\N	500	15	0	0
0ff49be4-3dbe-4ca9-a70f-3a26b5f0e64e	\N	\N	Gemini 2.5 Flash	f	t	0	\N	2026-06-01 06:48:12.495873+00	2026-06-01 06:48:12.495873+00	0ff49be4-3dbe-4ca9-a70f-3a26b5f0e64e	2	1	f	\N	f	\N	\N	\N	20	5	0	0
38c313f3-d383-4e5c-a0c8-31d17721bb24	\N	\N	Gemini 2.5 Flash Lite	f	t	0	\N	2026-06-01 06:53:08.118755+00	2026-06-01 06:53:08.118755+00	38c313f3-d383-4e5c-a0c8-31d17721bb24	3	1	f	\N	f	\N	\N	\N	20	10	0	0
8353d573-3dc6-4816-ad34-f56677dbdcf3	\N	\N	Gemini 3 Flash Preview	f	t	0	\N	2026-06-01 06:55:06.701171+00	2026-06-01 06:55:06.701171+00	8353d573-3dc6-4816-ad34-f56677dbdcf3	4	1	f	\N	f	\N	\N	\N	20	5	0	0
93792f40-341a-4de7-a4d8-856be4573d8f	\N	\N	Gemma 4 31b	f	t	0	\N	2026-06-01 07:03:49.814732+00	2026-06-01 07:03:49.814732+00	93792f40-341a-4de7-a4d8-856be4573d8f	5	1	f	\N	f	\N	\N	\N	1500	15	0	0
f4ac047f-6c03-44d7-9664-5ac2aba275ee	\N	\N	Gemma 4 26b	f	t	0	\N	2026-06-01 07:04:35.408646+00	2026-06-01 07:04:35.408646+00	f4ac047f-6c03-44d7-9664-5ac2aba275ee	6	1	f	\N	f	\N	\N	\N	1500	15	0	0
77c8d4b5-8dce-495c-9218-5ad7e49da687	\N	\N	Gemini 3.5 Flash	f	t	0	\N	2026-06-01 08:36:31.887602+00	2026-06-01 08:36:31.887602+00	77c8d4b5-8dce-495c-9218-5ad7e49da687	7	1	f	\N	f	\N	\N	\N	20	5	0	0
\.


--
-- Name: llm_model_profiles llm_model_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: graphrag_user
--

ALTER TABLE ONLY public.llm_model_profiles
    ADD CONSTRAINT llm_model_profiles_pkey PRIMARY KEY (id);


--
-- Name: llm_rotation_pools llm_rotation_pools_pkey; Type: CONSTRAINT; Schema: public; Owner: graphrag_user
--

ALTER TABLE ONLY public.llm_rotation_pools
    ADD CONSTRAINT llm_rotation_pools_pkey PRIMARY KEY (id);


--
-- Name: llm_rotation_pools uq_llm_rotation_pools_profile; Type: CONSTRAINT; Schema: public; Owner: graphrag_user
--

ALTER TABLE ONLY public.llm_rotation_pools
    ADD CONSTRAINT uq_llm_rotation_pools_profile UNIQUE (profile_id);


--
-- Name: ix_llm_rotation_pools_current; Type: INDEX; Schema: public; Owner: graphrag_user
--

CREATE INDEX ix_llm_rotation_pools_current ON public.llm_rotation_pools USING btree (current_position);


--
-- Name: ix_llm_rotation_pools_enabled_locked; Type: INDEX; Schema: public; Owner: graphrag_user
--

CREATE INDEX ix_llm_rotation_pools_enabled_locked ON public.llm_rotation_pools USING btree (is_enabled, is_locked);


--
-- Name: ix_llm_rotation_pools_order; Type: INDEX; Schema: public; Owner: graphrag_user
--

CREATE INDEX ix_llm_rotation_pools_order ON public.llm_rotation_pools USING btree (rotation_order);


--
-- Name: ix_llm_rotation_pools_quota_cooldown; Type: INDEX; Schema: public; Owner: graphrag_user
--

CREATE INDEX ix_llm_rotation_pools_quota_cooldown ON public.llm_rotation_pools USING btree (today_quota_exhausted, rate_limited_until);


--
-- Name: ix_llm_rotation_pools_scope_default; Type: INDEX; Schema: public; Owner: graphrag_user
--

CREATE INDEX ix_llm_rotation_pools_scope_default ON public.llm_rotation_pools USING btree (tenant_id, app_id, is_default);


--
-- Name: llm_model_profiles llm_model_profiles_api_key_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: graphrag_user
--

ALTER TABLE ONLY public.llm_model_profiles
    ADD CONSTRAINT llm_model_profiles_api_key_id_fkey FOREIGN KEY (api_key_id) REFERENCES public.ai_api_keys(id) ON DELETE RESTRICT;


--
-- Name: llm_model_profiles llm_model_profiles_model_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: graphrag_user
--

ALTER TABLE ONLY public.llm_model_profiles
    ADD CONSTRAINT llm_model_profiles_model_id_fkey FOREIGN KEY (model_id) REFERENCES public.ai_model_catalog(id) ON DELETE SET NULL;


--
-- Name: llm_model_profiles llm_model_profiles_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: graphrag_user
--

ALTER TABLE ONLY public.llm_model_profiles
    ADD CONSTRAINT llm_model_profiles_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.ai_providers(id) ON DELETE RESTRICT;


--
-- Name: llm_rotation_pools llm_rotation_pools_app_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: graphrag_user
--

ALTER TABLE ONLY public.llm_rotation_pools
    ADD CONSTRAINT llm_rotation_pools_app_id_fkey FOREIGN KEY (app_id) REFERENCES public.customer_apps(id) ON DELETE CASCADE;


--
-- Name: llm_rotation_pools llm_rotation_pools_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: graphrag_user
--

ALTER TABLE ONLY public.llm_rotation_pools
    ADD CONSTRAINT llm_rotation_pools_profile_id_fkey FOREIGN KEY (profile_id) REFERENCES public.llm_model_profiles(id) ON DELETE CASCADE;


--
-- Name: llm_rotation_pools llm_rotation_pools_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: graphrag_user
--

ALTER TABLE ONLY public.llm_rotation_pools
    ADD CONSTRAINT llm_rotation_pools_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict kf1SnxyWp6HhMRbv156pEDpK0CiMAkOycRogH80ySsbgrhudaImLdmOXlAkp8cP

