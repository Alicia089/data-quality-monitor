'use strict'

const Fastify = require('fastify')
const { execFile } = require('child_process')
const path = require('path')

const app = Fastify({ logger: true })

/**
 * POST /events
 *
 * Accepts a batch of analytics events from frontend or server-side sources,
 * runs them through the Python validation pipeline, and returns the result.
 *
 * Body: { source: string, events: Event[] }
 */
app.post('/events', {
  schema: {
    body: {
      type: 'object',
      required: ['source', 'events'],
      properties: {
        source: { type: 'string', minLength: 1 },
        events: { type: 'array', items: { type: 'object' }, minItems: 1 },
      },
    },
    response: {
      200: {
        type: 'object',
        properties: {
          run_id: { type: 'string' },
          total: { type: 'number' },
          valid: { type: 'number' },
          invalid: { type: 'number' },
          anomalies: { type: 'number' },
          error_rate_pct: { type: 'number' },
        },
      },
    },
  },
}, async (request, reply) => {
  const { source, events } = request.body

  const result = await runPipeline(source, events)
  return result
})

/**
 * GET /health
 */
app.get('/health', async () => ({ status: 'ok' }))

/**
 * GET /runs/summary
 * Returns error rate by source from the last 7 days (via psql).
 */
app.get('/runs/summary', async (_request, reply) => {
  const result = await queryDB('SELECT * FROM error_rate_by_source LIMIT 50')
  return { rows: result }
})

// ── Pipeline bridge ───────────────────────────────────────────────────────────

function runPipeline(source, events) {
  return new Promise((resolve, reject) => {
    const scriptPath = path.join(__dirname, '..', 'python', 'pipeline.py')
    const input = JSON.stringify({ source, events })

    const child = execFile('python', [scriptPath], { env: process.env }, (err, stdout, stderr) => {
      if (err) {
        reject(new Error(`Pipeline error: ${stderr || err.message}`))
        return
      }
      try {
        resolve(JSON.parse(stdout.trim()))
      } catch {
        reject(new Error(`Invalid pipeline output: ${stdout}`))
      }
    })

    child.stdin.write(input)
    child.stdin.end()
  })
}

function queryDB(sql) {
  return new Promise((resolve, reject) => {
    const { Client } = require('pg')
    const client = new Client({
      host: process.env.DB_HOST || 'localhost',
      port: parseInt(process.env.DB_PORT || '5432'),
      database: process.env.DB_NAME || 'dq_monitor',
      user: process.env.DB_USER || 'postgres',
      password: process.env.DB_PASSWORD || '',
    })
    client.connect()
      .then(() => client.query(sql))
      .then(res => { resolve(res.rows); client.end() })
      .catch(err => { reject(err); client.end() })
  })
}

// ── Start ─────────────────────────────────────────────────────────────────────

const start = async () => {
  const port = parseInt(process.env.PORT || '3000')
  try {
    await app.listen({ port, host: '0.0.0.0' })
  } catch (err) {
    app.log.error(err)
    process.exit(1)
  }
}

start()
