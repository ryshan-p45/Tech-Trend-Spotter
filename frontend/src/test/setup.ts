import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
// Adds DOM matchers like toBeInTheDocument() to every test file
import '@testing-library/jest-dom/vitest'

// Unmount rendered components after each test (not automatic without vitest globals),
// so one test's DOM never leaks into the next
afterEach(() => cleanup())
