Component({
  properties: {
    food: {
      type: Object,
      value: {},
    },
  },
  methods: {
    openDetail() {
      const food = this.properties.food as { id?: number }
      if (food.id) this.triggerEvent('open', { id: food.id })
    },
  },
})
