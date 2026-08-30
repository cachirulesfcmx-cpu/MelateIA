-- Verificación del endurecimiento RLS (v5, adaptado a este proyecto).
-- Esperado: rowsecurity = true en las 15 tablas, una política por tabla
-- SOLO para el rol del backend, y cero permisos para anon/authenticated.
SELECT schemaname, tablename, rowsecurity
FROM pg_tables WHERE schemaname='melateai' ORDER BY tablename;

SELECT tablename, policyname, roles::text, cmd
FROM pg_policies WHERE schemaname='melateai' ORDER BY tablename;

SELECT grantee, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema='melateai' AND grantee IN ('anon','authenticated')
ORDER BY table_name, grantee;
