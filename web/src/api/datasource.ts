import { request } from '@/api/http'

export interface Datasource {
  id: string
  name: string
  db_type: string
  host: string
  port: number | null
  database: string
  username: string
  jdbc_url: string | null
  structure_json: StructureDoc | null
  created_at: string | null
  updated_at: string | null
}

export interface ColumnInfo {
  name: string
  type?: string
  comment?: string | null
  nullable?: boolean
  primaryKey?: boolean
  primary_key?: boolean
  size?: number | null
}

export interface TableInfo {
  name?: string
  tableName?: string
  comment?: string | null
  tableComment?: string | null
  imported?: boolean
  enabled?: boolean
  sourceTableName?: string
  columns?: ColumnInfo[]
}

export interface StructureDoc {
  tables?: TableInfo[]
}

export interface AuthTable {
  name: string
  comment: string
  imported: boolean
  enabled: boolean
  columns: ColumnInfo[]
}

export interface DatasourceInput {
  name: string
  db_type: string
  host?: string
  port?: number | null
  database?: string
  username?: string
  password?: string
  jdbc_url?: string | null
}

export interface ConnectionTestResult {
  ok: boolean
  message: string
  latency_ms: number | null
}

export const DB_TYPES = [
  { label: 'SQLite', value: 'sqlite' },
  { label: 'MySQL', value: 'mysql' },
  { label: 'MariaDB', value: 'mariadb' },
  { label: 'PostgreSQL', value: 'postgres' },
  { label: 'Oracle', value: 'oracle' },
  { label: 'SQL Server', value: 'sqlserver' },
]

export function databasePlaceholder(dbType: string): string {
  if (dbType === 'sqlite') return 'SQLite 文件路径，例如 /tmp/askdata-orders.db'
  if (dbType === 'oracle') return 'Oracle 服务名，例如 FREEPDB1'
  if (dbType === 'sqlserver') return 'SQL Server 数据库名'
  return '库名'
}

export function listDatasources() {
  return request<Datasource[]>('/api/v1/datasources')
}

export function getDatasource(id: string) {
  return request<Datasource>(`/api/v1/datasources/${id}`)
}

export function createDatasource(payload: DatasourceInput) {
  return request<Datasource>('/api/v1/datasources', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateDatasource(id: string, payload: Partial<DatasourceInput>) {
  return request<Datasource>(`/api/v1/datasources/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function deleteDatasource(id: string) {
  return request<null>(`/api/v1/datasources/${id}`, { method: 'DELETE' })
}

export function testDatasourceBody(payload: DatasourceInput) {
  return request<ConnectionTestResult>('/api/v1/datasources/test', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function testDatasource(id: string) {
  return request<ConnectionTestResult>(`/api/v1/datasources/${id}/test`, {
    method: 'POST',
  })
}

export function introspectDatasource(id: string) {
  return request<StructureDoc>(`/api/v1/datasources/${id}/introspect`, {
    method: 'POST',
  })
}

export function getStructure(id: string) {
  return request<StructureDoc | null>(`/api/v1/datasources/${id}/structure`)
}

export function saveStructure(id: string, structure: StructureDoc) {
  return request<StructureDoc>(`/api/v1/datasources/${id}/structure`, {
    method: 'PUT',
    body: JSON.stringify({ structureJson: structure }),
  })
}

export function tableNameOf(table: TableInfo): string {
  return String(table.name || table.tableName || '').trim()
}

export function toAuthTables(doc: StructureDoc | null | undefined): AuthTable[] {
  const tables: AuthTable[] = []
  for (const table of doc?.tables || []) {
    const name = tableNameOf(table)
    if (!name) continue
    tables.push({
      name,
      comment: String(table.comment || table.tableComment || ''),
      imported: table.imported !== false,
      enabled: table.enabled !== false,
      columns: table.columns || [],
    })
  }
  return tables
}

export function mergeLiveTables(
  live: StructureDoc | null,
  prior: AuthTable[],
  preservePrior: boolean,
): AuthTable[] {
  const priorByName = new Map(prior.map((table) => [table.name.toLowerCase(), table]))
  const merged: AuthTable[] = []
  for (const table of live?.tables || []) {
    const name = tableNameOf(table)
    if (!name) continue
    const previous = priorByName.get(name.toLowerCase())
    merged.push({
      name,
      comment: String(table.comment || table.tableComment || previous?.comment || ''),
      imported: preservePrior ? Boolean(previous?.imported) : table.imported !== false,
      enabled: preservePrior ? Boolean(previous?.enabled) : table.enabled !== false,
      columns: table.columns || previous?.columns || [],
    })
  }
  return merged
}

export function toStructureDoc(tables: AuthTable[]): StructureDoc {
  return {
    tables: tables.map((table) => ({
      name: table.name,
      tableName: table.name,
      comment: table.comment,
      tableComment: table.comment,
      imported: table.imported,
      enabled: table.enabled,
      columns: table.columns,
    })),
  }
}

export function datasourceLocation(item: Pick<Datasource, 'db_type' | 'host' | 'port' | 'database'>): string {
  if ((item.db_type || '').toLowerCase() === 'sqlite') {
    return item.database || '内存库'
  }
  const host = item.host || 'localhost'
  const port = item.port ? `:${item.port}` : ''
  const database = item.database ? ` / ${item.database}` : ''
  return `${host}${port}${database}`
}
