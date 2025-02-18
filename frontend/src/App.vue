<template>
  <div class="p-4 bg-gray-100 min-h-screen">
    <h1 class="text-2xl font-bold text-blue-600">
      {{ message }}
    </h1>
    <button @click="fetchMessage" class="mt-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600">
      새로고침
    </button>
  </div>
</template>

<script>
export default {
  data() {
    return {
      message: ''
    }
  },
  methods: {
    async fetchMessage() {
      try {
        const response = await fetch(`${import.meta.env.VITE_API_URL}/`, {
          cache: 'no-store',  // 캐시 사용하지 않음
          headers: {
            'Cache-Control': 'no-cache'
          }
        })
        const data = await response.json()
        this.message = data.message
      } catch (error) {
        console.error('Error fetching message:', error)
        this.message = 'Error loading message'
      }
    }
  },
  mounted() {
    this.fetchMessage()
  }
}
</script> 