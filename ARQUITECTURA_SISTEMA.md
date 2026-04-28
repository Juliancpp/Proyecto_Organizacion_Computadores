# Documentación Técnica: Simulador de Arquitecturas CPU (RISC vs CISC vs x86-64)

## 1. Descripción General

Este sistema es un simulador completo de arquitecturas de computadoras que permite:

- Ejecutar programas en ensamblador de diferentes arquitecturas (RISC, CISC, x86-64)
- Visualizar la ejecución ciclo por ciclo
- Comparar rendimiento entre arquitecturas
- Analizar pipelines y dependencias de datos
- Aprender conceptos de arquitectura de computadores mediante simulación visual

### Objetivo Principal
Proporcionar una plataforma educativa y de análisis para entender las diferencias fundamentales entre arquitecturas RISC (Reduced Instruction Set Computer) y CISC (Complex Instruction Set Computer), incluyendo soporte nativo para x86-64 NASM.

---

## 2. Arquitectura del Sistema (Alto Nivel)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CAPA DE PRESENTACIÓN                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │   Editor     │  │  Visualizador │  │   Métricas   │  │   Timeline    │   │
│  │   Código     │  │    Diagrama  │  │   CPI/Ciclos │  │   Ciclo/Ciclo│   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
└─────────┼─────────────────┼─────────────────┼─────────────────┼───────────┘
          │                 │                 │                 │
          └─────────────────┴────────┬────────┴─────────────────┘
                                     │
                              [HTTP/REST API]
                                     │
┌────────────────────────────────────┴─────────────────────────────────────┐
│                           CAPA DE APLICACIÓN                               │
│                              (Django REST)                                   │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    ENDPOINTS API                                         │ │
│  │  POST /api/simulate/      → Simulación unificada                       │ │
│  │  POST /api/simulate/risc/ → Solo arquitectura RISC                     │ │
│  │  POST /api/simulate/cisc/ → Solo arquitectura CISC                     │ │
│  │  POST /api/simulate/x86/  → Solo arquitectura x86-64                  │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                       │
│  ┌───────────────────────────────────┴────────────────────────────────────┐ │
│  │                         CAPA DE NEGOCIO                                 │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │ │
│  │  │  Validador  │  │  Detector   │  │  Parser     │  │   Engines   │    │ │
│  │  │   Request   │  │Arquitectura │  │  Assembly   │  │             │    │ │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘    │ │
│  └─────────┼─────────────────┼─────────────────┼─────────────────┼──────────┘ │
└────────────┼─────────────────┼─────────────────┼─────────────────┼──────────┘
             │                 │                 │                 │
             ▼                 ▼                 ▼                 ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │                        CAPA DE SIMULACIÓN                               │
  │                                                                          │
  │   ┌──────────────┐      ┌──────────────┐      ┌──────────────┐          │
  │   │  RISC Engine │      │  CISC Engine │      │  x86-64      │          │
  │   │              │      │              │      │  Engine      │          │
  │   │  • Parser    │      │  • Parser    │      │  • Parser    │          │
  │   │  • Executor  │      │  • Decoder   │      │  • NASM      │          │
  │   │  • Pipeline  │      │  • µOps      │      │    Parser    │          │
  │   │              │      │  • Executor  │      │  • Executor  │          │
  │   └──────────────┘      └──────────────┘      │  • Memory    │          │
  │                                               │    Model     │          │
  │                                               └──────────────┘          │
  └────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Flujo Completo del Sistema (End-to-End)

### Paso 1: Usuario (Frontend)
```
[USUARIO]
    │
    ├── Escribe código ensamblador en editor
    │   ├── Opción A: Código RISC (MOV, ADD, SUB, etc.)
    │   ├── Opción B: Código CISC (instrucciones complejas)
    │   └── Opción C: Código x86-64 NASM (section .data, mov rax, etc.)
    │
    ├── Selecciona arquitectura: [AUTO | RISC | CISC | x86]
    │
    └── Presiona "Run"
```

### Paso 2: Frontend React
```
[FRONTEND - React + TypeScript]
    │
    ├── Toolbar.tsx detecta código x86 mediante regex:
    │   /\b(section \.data|section \.text|rax|rbx|rcx|mov|syscall)\b/i
    │
    ├── Si auto-detectado → architecture = "x86"
    │   Si no → usa selección del usuario
    │
    ├── Construye payload:
    │   {
    │     code: "...",
    │     architecture: "x86",  // "risc" | "cisc" | "x86" | "auto"
    │     step: false,
    │     pipeline: false,
    │     transpile: false      // true solo para RISC/CISC
    │   }
    │
    └── POST /api/simulate/
```

### Paso 3: API Request (HTTP)
```
[HTTP REQUEST]
    │
    POST http://localhost:8000/api/simulate/
    Content-Type: application/json
    │
    Body: { code, architecture, step, pipeline, transpile }
```

### Paso 4: Backend Django REST
```
[BACKEND - Django REST Framework]
    │
    ├── SimulateView.post() recibe request
    │
    ├── SimulationRequestSerializer valida:
    │   ├── code: string
    │   ├── architecture: enum ["risc", "cisc", "x86", "auto"]
    │   └── opcionales: step, pipeline, transpile
    │
    ├── Si x86 detectado:
    │   └── Desactiva transpile automáticamente
    │
    ├── Enruta a engine según architecture:
    │   ├── "risc" → _run_risc(code)
    │   ├── "cisc" → _run_cisc(code)
    │   ├── "x86"  → _run_x86(code)
    │   └── "auto" → Detecta y ejecuta todos los compatibles
    │
    └── Retorna JSON unificado
```

### Paso 5: Engine x86-64 (Ejemplo Completo)
```
[ENGINE x86-64 - Flujo Detallado]
    │
    A. PARSE PHASE
    │   ├── parse_x86(code)
    │   │   ├── Separa secciones .data y .text
    │   │   ├── Parsea .data:
    │   │   │   ├── "array dd 34, 7, 23..." → DataSymbol
    │   │   │   ├── "n equ ($ - array) / 4" → Constante n=6
    │   │   │   └── Genera segmento de datos en 0x1000
    │   │   ├── Parsea .text:
    │   │   │   ├── Extrae labels: _start → índice 0
    │   │   │   ├── outer_loop → índice 2
    │   │   │   ├── inner_loop → índice 5
    │   │   │   └── Mapea labels a índices de instrucción
    │   │   └── Parsea instrucciones:
    │   │       ├── "mov r8, n" → X86Instruction(opcode="mov", operands=["r8", 6])
    │   │       ├── "mov eax, [array + rcx*4]" → MemoryOperand
    │   │       └── "jl inner_loop" → JUMP con referencia a label
    │   │
    │   └── Retorna X86ParseResult:
    │       ├── instructions: list[X86Instruction]
    │       ├── labels: dict[str, int]
    │       ├── data_symbols: dict[str, DataSymbol]
    │       └── constants: dict[str, int]
    │
    B. EXECUTION PHASE
    │   ├── execute_x86(parse_result)
    │   │   ├── Inicializa X86State:
    │   │   │   ├── registers = {rax:0, rbx:0, rcx:0, ... r15:0}
    │   │   │   ├── flags = {ZF:false, SF:false, OF:false, CF:false}
    │   │   │   ├── memory = bytearray(64KB)
    │   │   │   ├── pc = labels.get("_start", 0)
    │   │   │   ├── halted = false
    │   │   │   └── cycles = 0
    │   │   │
    │   │   ├── Carga segmento de datos en memoria:
    │   │   │   └── memory[0x1000:0x1018] = bytes de array
    │   │   │
    │   │   └── BUCLE PRINCIPAL DE EJECUCIÓN:
    │   │       while not halted and pc < len(instructions):
    │   │           │
    │   │           1. FETCH
    │   │           │   instr = instructions[pc]
    │   │           │
    │   │           2. NEW CYCLE (crea snapshot)
    │   │           │   state.new_cycle(instr.raw)  ← guarda PC e instrucción
    │   │           │   → Crea CPUSnapshot en core_state.timeline
    │   │           │
    │   │           3. DECODE + EXECUTE
    │   │           │   _execute_instruction(state, instr, labels, data_symbols)
    │   │           │   ├── mov: lee operands, escribe destino
    │   │           │   ├── cmp: lee operands, actualiza flags, no escribe
    │   │           │   ├── jl: evalúa flags (SF≠OF), salta si true
    │   │           │   ├── inc: incrementa, actualiza flags
    │   │           │   └── syscall: si rax=60 → halted=true
    │   │           │
    │   │           4. UPDATE PC
    │   │           │   Si instrucción es JUMP y condición tomada:
    │   │           │       pc = labels[label]  ← salta
    │   │           │   Si instrucción es syscall:
    │   │           │       pc no avanza (programa termina)
    │   │           │   Si no:
    │   │           │       pc += 1  ← siguiente instrucción
    │   │           │
    │   │           5. END CYCLE
    │   │               state.end_cycle()
    │   │               cycles += 1
    │   │               Si cycles > MAX_CYCLES (100,000):
    │   │                   raise ExecutionError("Infinite loop detected")
    │   │
    │   └── Retorna X86State final:
    │       ├── registers (modificados)
    │       ├── memory (array ordenado)
    │       ├── flags (estado final)
    │       ├── pc (índice final)
    │       ├── cycles (159 para bubble sort)
    │       └── halted (true)
    │
    C. FORMAT RESPONSE
        ├── Lee arrays desde memoria:
        │   └── array = read_array_from_memory(state, data_symbols["array"])
        │       → [5, 7, 23, 32, 34, 62]
        │
        ├── Construye timeline:
        │   └── [s.to_dict() for s in state.core_state.timeline]
        │       → [{cycle:1, pc:0, ...}, {cycle:2, pc:1, ...}, ...]
        │
        └── Retorna JSON:
            {
              "x86": {
                "timeline": [...],           // 159 entradas
                "final_state": {
                  "pc": 20,
                  "registers": {"rax":60, "r8":1, ...},
                  "flags": {"ZF":true, "SF":false, ...},
                  "halted": true,
                  "cycles": 159
                },
                "arrays": {"array":[5,7,23,32,34,62]},
                "cycles": 159,
                "parsed_instructions": {...}
              }
            }
```

### Paso 6: Respuesta al Frontend
```
[RESPONSE JSON]
    │
    HTTP 200 OK
    │
    {
      "x86": {
        "cycles": 159,
        "halted": true,
        "timeline": [
          {
            "cycle": 1,
            "pc": 0,
            "registers": [0,0,0...],
            "events": [{"component":"REGISTERS", "action":"mov r8 ← 6"}]
          },
          {
            "cycle": 80,
            "pc": 12,
            "registers": [...],
            "events": [...]
          },
          ...159 entradas
        ],
        "final_state": {
          "registers": {"rax":60, "rbx":7, "r8":1, ...},
          "arrays": {"array":[5,7,23,32,34,62]},
          "halted": true
        }
      }
    }
```

### Paso 7: Renderizado Frontend
```
[FRONTEND - Renderizado]
    │
    ├── Recibe response
    │
    ├── setResult(response) → actualiza estado global
    │
    ├── useEffect detecta result.x86 y activeArch="x86"
    │   └── setActiveTab("x86")  ← cambia a pestaña x86
    │
    ├── X86Results.tsx renderiza:
    │   ├── Header: "x86-64 Simulation Results"
    │   ├── Summary Cards: Cycles, Instructions, Halted, Timeline
    │   ├── Data Arrays: array = [5, 7, 23, 32, 34, 62]
    │   ├── Registers: rax=60, r8=1, rcx=1, ...
    │   ├── Flags: ZF=1, SF=0, OF=0, CF=0
    │   └── Timeline: Lista de 159 ciclos con PC e instrucciones
    │
    └── Badge en tab "x86-64" muestra: "159" (número de ciclos)
```

---

## 4. Detalle de Componentes Principales

### 4.1 Auto-Detector de Arquitectura

```python
# Implementación: simulator/x86/parser.py

def is_x86_syntax(source: str) -> bool:
    """
    Heurística de detección de código x86-64 NASM.
    """
    lower = source.lower()
    
    # Detecta directivas de sección
    if "section .data" in lower or "section .text" in lower:
        return True
    
    # Detecta registros x86-64
    if re.search(r'\b(rax|rbx|rcx|rdx|rsi|rdi|eax|ebx|ecx|edx|syscall)\b', lower):
        return True
    
    return False

# Flujo de decisión:
# 1. Usuario selecciona "auto"
# 2. Frontend llama a isX86Code(code) localmente
# 3. Si detecta x86 → architecture = "x86"
# 4. Si no → architecture = "auto" (backend prueba RISC y CISC)
```

### 4.2 Parser x86-64

```python
class X86ParseResult:
    """Resultado del parsing de código x86-64."""
    
    instructions: list[X86Instruction]  # 21 instrucciones para bubble sort
    labels: dict[str, int]            # {"_start": 0, "outer_loop": 2, ...}
    data_symbols: dict[str, DataSymbol]  # {"array": DataSymbol(...)}
    constants: dict[str, int]         # {"n": 6}
    data_segment: bytes               # 24 bytes (6 dwords)
    data_base_address: int = 0x1000  # Dirección base de .data

@dataclass
class X86Instruction:
    """Instrucción x86-64 parseada."""
    
    opcode: str      # "mov", "cmp", "jl", etc.
    operands: list   # ["r8", 6] o ["eax", MemoryOperand(...)]
    raw: str         # Texto original: "mov r8, n"
    line_number: int # Para debugging

@dataclass
class MemoryOperand:
    """Operando de memoria: [base + index*scale + displacement]."""
    
    base_symbol: str | None     # "array"
    base_reg: str | None        # "rbx"
    index_reg: str | None       # "rcx"
    scale: int = 1              # 4
    displacement: int = 0       # 0 o 4
```

### 4.3 X86State (Modelo de CPU)

```python
class X86State:
    """
    Estado completo de la CPU x86-64 en un momento dado.
    """
    
    # ── Registros de propósito general (64-bit) ──
    registers: dict[str, int] = {
        "rax": 0, "rbx": 0, "rcx": 0, "rdx": 0,
        "rsi": 0, "rdi": 0, "rsp": 0, "rbp": 0,
        "r8": 0,  "r9": 0,  "r10": 0, "r11": 0,
        "r12": 0, "r13": 0, "r14": 0, "r15": 0,
    }
    
    # ── Registros de 32-bit (alias) ──
    # eax = rax & 0xFFFFFFFF (escritura zero-extends a rax)
    
    # ── FLAGS ──
    flags: dict[str, bool] = {
        "ZF": False,  # Zero Flag (resultado fue cero)
        "SF": False,  # Sign Flag (resultado negativo)
        "OF": False,  # Overflow Flag (overflow con signo)
        "CF": False,  # Carry Flag (carry/borrow sin signo)
    }
    
    # ── Memoria ──
    memory: bytearray      # 64KB direccionable por bytes
    memory_size: int = 65536
    
    # ── Estado de ejecución ──
    pc: int = 0            # Program Counter (índice de instrucción)
    halted: bool = False   # CPU detenida
    cycles: int = 0        # Contador de ciclos ejecutados
    
    # ── Integración con core CPUState ──
    core_state: CPUState   # Para timeline y snapshots
    
    # ── Log de salida ──
    output_log: list[dict]  # Eventos de salida

    def new_cycle(self, current_instruction: str = "") -> int:
        """
        Inicia nuevo ciclo. Sincroniza PC e instrucción a core_state
        para que el timeline capture el estado correcto.
        """
        self.cycles += 1
        self.core_state.cycles = self.cycles
        self.core_state.pc = self.pc                    # ← SINCRONIZACIÓN CRÍTICA
        self.core_state.current_instruction = current_instruction
        return self.core_state.new_cycle()
```

---

## 5. Flujo de Ejecución Paso a Paso

### Ciclo de Vida de una Instrucción (Ejemplo: `mov r8, n`)

```
Ciclo N: mov r8, n
══════════════════════════════════════════════════════════════════════════

1. FETCH
   ├── pc = 0 (desde _start)
   ├── instr = instructions[0]
   └── instr.raw = "mov r8, n"

2. NEW CYCLE (Snapshot inicial)
   ├── cycles = 1
   ├── core_state.pc = 0          ← Guarda PC actual
   ├── core_state.current_instruction = "mov r8, n"
   └── Crea CPUSnapshot en timeline[0]

3. DECODE + EXECUTE
   ├── _exec_mov(state, ["r8", 6], ...)
   │   ├── Lee src: 6 (constante n)
   │   ├── Escribe dst: state.registers["r8"] = 6
   │   └── Event: REGISTERS "mov r8 ← 6"
   └── No modifica flags

4. UPDATE PC
   └── pc += 1  →  pc = 1

5. END CYCLE
   ├── Commit del snapshot
   └── timeline[0] = {cycle:1, pc:0, events:[...]}

Ciclo N+1: dec r8
══════════════════════════════════════════════════════════════════════════

1. FETCH
   ├── pc = 1
   └── instr = instructions[1]  # "dec r8"

2. NEW CYCLE
   ├── cycles = 2
   ├── core_state.pc = 1
   └── ...

3. EXECUTE
   ├── valor anterior: r8 = 6
   ├── nuevo valor: r8 = 5
   ├── Actualiza flags: ZF=false, SF=false
   └── Event: ALU "dec r8 = 6 → 5"

4. UPDATE PC
   └── pc += 1  →  pc = 2

5. END CYCLE
   └── timeline[1] = {cycle:2, pc:1, ...}

Ciclo K: jl inner_loop (SALTO CONDICIONAL)
══════════════════════════════════════════════════════════════════════════

1. FETCH
   └── instr = "jl inner_loop"

2. NEW CYCLE
   └── Guarda PC actual (ej: pc = 11)

3. EXECUTE
   ├── Evalúa condición: flags.SF != flags.OF
   ├── Resultado: true (debe saltar)
   ├── _exec_jump actualiza:
   │   state.pc = labels["inner_loop"]  # pc = 5
   └── Event: PC "JL TAKEN: PC ← 5"

4. NO UPDATE PC (ya fue actualizado por jump)
   └── return  (sin pc += 1)

5. END CYCLE
   └── Próximo fetch será instructions[5]

Ciclo Final: syscall (sys_exit)
══════════════════════════════════════════════════════════════════════════

1. FETCH
   └── instr = "syscall"

2. NEW CYCLE
   └── Guarda PC (ej: pc = 20)

3. EXECUTE
   ├── Lee rax = 60 (sys_exit)
   ├── Lee rdi = 0 (exit code)
   ├── state.halted = true
   └── Event: CONTROL "SYSCALL 60 (exit): code=0"

4. NO UPDATE PC
   └── return

5. END CYCLE + EXIT
   └── halted = true → while loop termina
```

---

## 6. Manejo de Ciclos y Timeline

### Estructura de Timeline

```typescript
// Cada entrada representa un ciclo de reloj completo
interface TimelineCycle {
  cycle: number;           // Número de ciclo (1, 2, 3, ...)
  pc: number;              // Program Counter durante este ciclo
  registers: number[];     // Valores de registros (para RISC/CISC)
  memory: Record<string, number>;  // Memoria
  halted: boolean;
  events: SimEvent[];      // Eventos ocurridos
  control_signals: Record<string, any>;
  current_instruction: string;  // Instrucción ejecutada
}

interface SimEvent {
  component: "CONTROL" | "PC" | "REGISTERS" | "ALU" | "BUS" | "MEMORY";
  action: string;          // Descripción legible
  inputs: any[];          // Entradas
  output: any;            // Resultado
  meta?: EventMeta;       // Metadatos adicionales
}
```

### Generación de Timeline (Immutabilidad)

```python
# Cada ciclo crea un NUEVO estado (inmutabilidad)

def new_cycle():
    """
    Crear snapshot inmutable del estado actual.
    """
    # 1. Crear nuevo ciclo en core_state
    cycle_number = self.cycles + 1
    
    # 2. Snapshot del estado actual
    snapshot = CPUSnapshot(
        cycle=cycle_number,
        pc=self.pc,                    # ← PC actual
        registers=copy(self.registers), # ← Copia de registros
        memory=self.memory.copy(),      # ← Copia de memoria
        halted=self.halted,
        events=[],                     # ← Se llenan durante ejecución
        current_instruction=""         # ← Se setea antes de ejecutar
    )
    
    # 3. Agregar a timeline
    self.core_state.timeline.append(snapshot)
    
    # 4. Ejecutar instrucción (modifica self, no el snapshot)
    execute_current_instruction()
    
    # 5. Finalizar ciclo (commit)
    snapshot.events = self.current_events
```

---

## 7. Diferencias RISC vs CISC vs x86

| Aspecto | RISC Engine | CISC Engine | x86-64 Engine |
|---------|-------------|-------------|---------------|
| **ISA** | Simple (MOV, ADD, SUB, MUL, DIV, LOAD, STORE, HALT) | Compleja (instrucciones de múltiples operaciones) | x86-64 NASM (real) |
| **Registros** | R0-R7 (8 registros) | R0-R15 (16 registros) | rax-r15 (16 x 64-bit) |
| **Memoria** | Modelo Harvard simplificado | Von Neumann | Plana, byte-addressable |
| **Instrucciones** | 1 ciclo por instrucción | 1-3 ciclos (µops) | Variable (1 ciclo en simulador) |
| **Pipeline** | 5 etapas opcional | No aplica | No aplica (ejecución directa) |
| **µOps** | No aplica | Descompone en micro-operaciones | No aplica |
| **Secciones** | No | No | .data, .text |
| **Labels** | Soporte básico | Soporte básico | Completo (NASM-style) |
| **Memoria** | Direccionamiento simple | Direccionamiento complejo | [base + index*scale + disp] |
| **Syscalls** | HALT | HALT | syscall (rax=60 exit) |
| **Flags** | No | Simplificado | Completo (ZF, SF, OF, CF) |

---

## 8. Pipeline (RISC únicamente)

```
5 ETAPAS DEL PIPELINE RISC:
══════════════════════════════════════════════════════════════════════════

Instrucción N:    [IF]→[ID]→[EX]→[MEM]→[WB]
Instrucción N+1:      [IF]→[ID]→[EX]→[MEM]→[WB]
Instrucción N+2:          [IF]→[ID]→[EX]→[MEM]→[WB]

IF  = Instruction Fetch      (Buscar instrucción)
ID  = Instruction Decode     (Decodificar)
EX  = Execute               (Ejecutar en ALU)
MEM = Memory Access         (Leer/escribir memoria)
WB  = Write Back            (Escribir resultado en registro)

HAZARDS:
────────
• Data Hazard: Instrucción necesita resultado anterior
  Solución: Stalling (esperar) o Forwarding

• Control Hazard: Salto condicional
  Solución: Predicción o Flush del pipeline

• Structural Hazard: Recurso ocupado
  Solución: Stalling
```

---

## 9. Manejo de Errores

### Jerarquía de Errores

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ERRORES DE VALIDACIÓN                               │
│  HTTP 400 - Bad Request                                                       │
│  ├── Campos requeridos faltantes (code, architecture)                       │
│  ├── Tipo de dato inválido                                                    │
│  └── JSON malformado                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                           ERRORES DE PARSING                                  │
│  HTTP 400 con detalles                                                        │
│  ├── Instrucción desconocida en línea X                                       │
│  ├── Label duplicado                                                          │
│  ├── Referencia a símbolo indefinido                                          │
│  └── Expresión equ inválida                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                          ERRORES DE EJECUCIÓN                                 │
│  HTTP 400 o 500                                                                 │
│  ├── Division por cero                                                          │
│  ├── Acceso a memoria fuera de rango                                            │
│  ├── Salto a label inexistente                                                  │
│  ├── Infinite loop detectado (>100,000 ciclos)                                  │
│  └── Syscall no implementado                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                          ERRORES DE SISTEMA                                   │
│  HTTP 500 - Internal Server Error                                               │
│  ├── Excepción no manejada                                                      │
│  ├── Error de base de datos (si aplica)                                       │
│  └── Error de IO                                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Casos de Uso

### Caso 1: Bubble Sort x86-64
```
Input:  Código NASM con array desordenado
        [34, 7, 23, 32, 5, 62]

Output: Array ordenado
        [5, 7, 23, 32, 34, 62]
        
Métricas:
- Ciclos: 159
- Instrucciones ejecutadas: ~80
- Estado final: halted=true, rax=60
```

### Caso 2: Comparación RISC vs CISC
```
Input:  Mismo programa (suma de 1 a 10)

RISC:
- Instrucciones: 15
- Ciclos: 15 (sin pipeline) o menos (con pipeline)

CISC:
- Instrucciones: 8
- Ciclos: 12 (algunas instrucciones toman 2 ciclos)

Comparación:
- RISC más rápido en tiempo de ciclo
- CISC menos instrucciones
```

---

## 11. Diagrama de Flujo en Formato Texto

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USUARIO                                         │
│                    (Escribe código en editor)                                │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            FRONTEND (React)                                  │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐               │
│  │   EditorPanel   │  │   Auto-Detect   │  │     Toolbar     │               │
│  │   (CodeMirror)  │──│  (Regex x86?)   │──│  (Botón Run)    │               │
│  └─────────────────┘  └─────────────────┘  └────────┬──────────┘               │
└───────────────────────────────────────────────────┼──────────────────────────┘
                                                    │
                    POST /api/simulate/             │
                    {code, architecture}            │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BACKEND (Django REST)                                 │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │                     SimulationRequestSerializer                       │     │
│  │  • Valida código (string no vacío)                                  │     │
│  │  • Valida architecture (risc|cisc|x86|auto)                          │     │
│  │  • Asigna defaults (step=false, pipeline=false)                       │     │
│  └───────────────────────────────┬─────────────────────────────────────┘     │
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │   is_x86_syntax(code)?  │
                    └───────────┬─────────────┘
                                │
              ┌──────────────────┼──────────────────┐
              │ Sí                             │ No
              ▼                                ▼
    ┌─────────────────────┐        ┌─────────────────────────────┐
    │  Desactiva transpile │        │  Intenta RISC y CISC         │
    │  Ejecuta x86 Engine  │        │  con transpilación opcional  │
    └──────────┬──────────┘        └──────────────┬─────────────┘
               │                                   │
               └─────────────────┬─────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CAPA DE SIMULACIÓN                                 │
│                                                                              │
│  ┌─────────────────────────┐  ┌─────────────────────────┐  ┌───────────────┐ │
│  │      PARSER PHASE        │  │    EXECUTION PHASE      │  │  FORMAT PHASE │ │
│  │                          │  │                          │  │               │ │
│  │  • Split .data/.text     │  │  • Init X86State         │  │ • Read arrays │ │
│  │  • Parse labels          │  │  • Load data segment     │  │ • Build       │ │
│  │  • Parse dd/equ          │  │  • WHILE not halted:     │  │   timeline    │ │
│  │  • Parse instructions    │  │    - FETCH              │  │ • Serialize   │ │
│  │  • MemoryOperand         │  │    - NEW CYCLE          │  │   to JSON     │ │
│  │    [base+index*scale+disp]│  │    - EXECUTE            │  │               │ │
│  │                          │  │    - UPDATE PC          │  │               │ │
│  │                          │  │    - END CYCLE          │  │               │ │
│  └───────────┬──────────────┘  └───────────┬──────────────┘  └───────┬───────┘ │
│              │                            │                        │         │
│              └────────────────────────────┼────────────────────────┘         │
│                                           │                                  │
└───────────────────────────────────────────┼──────────────────────────────────┘
                                              │
                                              ▼
                                    ┌─────────────────┐
                                    │   X86State final  │
                                    │   • registers     │
                                    │   • memory        │
                                    │   • timeline[]    │
                                    │   • cycles = 159  │
                                    │   • halted = true │
                                    └────────┬────────┘
                                             │
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RESPUESTA HTTP (JSON)                                │
│                                                                              │
│  HTTP 200 OK                                                                 │
│  {                                                                            │
│    "x86": {                                                                   │
│      "cycles": 159,                                                           │
│      "halted": true,                                                          │
│      "final_state": {                                                         │
│        "registers": {"rax":60, "r8":1, ...},                                   │
│        "flags": {"ZF":true, ...},                                             │
│        "halted": true                                                         │
│      },                                                                       │
│      "arrays": {"array":[5,7,23,32,34,62]},                                   │
│      "timeline": [                                                            │
│        {"cycle":1, "pc":0, "events":[...]},                                    │
│        {"cycle":2, "pc":1, "events":[...]},                                    │
│        ...                                                                    │
│      ]                                                                        │
│    }                                                                          │
│  }                                                                            │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Renderizado)                               │
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐               │
│  │   X86Results    │  │   MainLayout    │  │   EventsTab     │               │
│  │   Component     │  │   (Tab Switch)  │  │   (Timeline)    │               │
│  │                 │  │                 │  │                 │               │
│  │ • Cycles: 159   │  │ • Auto-switch   │  │ • Filter events │               │
│  │ • Array sorted  │  │   to x86 tab    │  │ • Show all      │               │
│  │ • Registers     │  │ • Badge: 159    │  │   cycles        │               │
│  │ • Timeline      │  │                 │  │                 │               │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. Diagrama en Mermaid (Copiar y pegar en Mermaid Live Editor)

```mermaid
flowchart TB
    subgraph "Frontend React"
        A[Usuario escribe código] --> B{Auto-detect x86?}
        B -->|Sí| C[Architecture = x86]
        B -->|No| D[Architecture = auto]
        C --> E[POST /api/simulate/]
        D --> E
    end

    subgraph "Backend Django"
        E --> F[SimulationRequestSerializer]
        F -->|Valida| G{Es x86?}
        G -->|Sí| H[_run_x86]
        G -->|No| I[_run_risc]
        G -->|No| J[_run_cisc]
    end

    subgraph "Engine x86-64"
        H --> K[parse_x86]
        K --> L[Extrae .data/.text]
        L --> M[Parsea labels]
        M --> N[Parsea instrucciones]
        N --> O[Genera X86ParseResult]
        O --> P[execute_x86]
        
        P --> Q[Init X86State]
        Q --> R{halted?}
        R -->|No| S[FETCH instrucción]
        S --> T[NEW CYCLE snapshot]
        T --> U[EXECUTE]
        
        U --> V{Tipo instrucción?}
        V -->|MOV| W[Write register]
        V -->|CMP| X[Update flags]
        V -->|JL| Y[Evalúa condición]
        Y -->|Jump taken| Z[PC = label]
        Y -->|No jump| AA[PC += 1]
        V -->|SYSCALL| AB[halted = true]
        
        W --> AA
        X --> AA
        Z --> AC[END CYCLE]
        AA --> AC
        AC --> R
        R -->|Sí| AD[Format response]
    end

    subgraph "Response"
        AD --> AE[JSON: {x86: {cycles, timeline, arrays}}]
    end

    subgraph "Frontend Render"
        AE --> AF[setResult]
        AF --> AG[Auto-switch a tab x86]
        AG --> AH[X86Results Component]
        AH --> AI[Display: Cycles, Registers, Timeline]
    end

    style H fill:#4a5568,stroke:#2d3748,stroke-width:2px,color:#fff
    style P fill:#2f855a,stroke:#276749,stroke-width:2px,color:#fff
    style AE fill:#c53030,stroke:#9b2c2c,stroke-width:2px,color:#fff
    style AH fill:#d69e2e,stroke:#b7791f,stroke-width:2px,color:#000
```

---

## 13. Glosario de Términos

| Término | Descripción |
|---------|-------------|
| **ISA** | Instruction Set Architecture - Conjunto de instrucciones que entiende la CPU |
| **PC** | Program Counter - Registro que indica la siguiente instrucción a ejecutar |
| **ALU** | Arithmetic Logic Unit - Unidad que ejecuta operaciones aritméticas y lógicas |
| **µOp** | Micro-operation - Operación primitiva interna de la CPU |
| **Pipeline** | Técnica de paralelismo donde múltiples instrucciones se ejecutan en etapas solapadas |
| **Hazard** | Condición que impide el avance normal del pipeline |
| **NASM** | Netwide Assembler - Ensamblador x86 popular |
| **DWord** | Double Word - 32 bits (4 bytes) |
| **QWord** | Quad Word - 64 bits (8 bytes) |
| **Syscall** | System Call - Interfaz entre programa y kernel del SO |
| **ZF/SF/OF/CF** | Zero Flag, Sign Flag, Overflow Flag, Carry Flag |
| **endianness** | Orden de bytes en memoria (little-endian en x86) |

---

## 14. Archivos Clave del Sistema

### Backend (Python/Django)
```
backend/simulator/
├── api/
│   ├── views.py           # Endpoints REST
│   └── serializers.py     # Validación de requests
├── x86/
│   ├── parser.py          # Parser NASM
│   ├── engine.py          # Ejecutor x86
│   └── state.py           # X86State (modelo CPU)
├── risc/
│   ├── parser.py          # Parser RISC
│   ├── engine.py          # Ejecutor RISC
│   └── pipeline.py        # Pipeline 5 etapas
└── cisc/
    ├── parser.py          # Parser CISC
    └── engine.py          # Ejecutor CISC (con µops)
```

### Frontend (React/TypeScript)
```
frontend/src/
├── components/
│   ├── MainLayout.tsx     # Layout principal con tabs
│   ├── Toolbar.tsx        # Botón Run + arquitectura
│   ├── X86Results.tsx     # Visualización x86
│   ├── MetricsTab.tsx     # Métricas comparativas
│   └── EventsTab.tsx      # Timeline de eventos
├── store/
│   └── simulationStore.ts # Estado global (Zustand)
├── types/
│   └── simulation.ts      # Interfaces TypeScript
└── lib/
    └── api.ts             # Cliente HTTP
```

---

**Fin del Documento Técnico**